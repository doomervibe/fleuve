"""Metrics for Fleuve workflows — Prometheus and/or OpenTelemetry.

This module provides comprehensive observability for the Fleuve framework,
including metrics for:
- Workflow event processing
- Command latency
- Actions executed/failed
- State load time
- Active workflows / pending delays / cache hit rate
- JetStream outbox publisher performance
- Event consumption and lag
- System health and errors

Both Prometheus (``prometheus_client``) and OpenTelemetry Metrics API
(``opentelemetry-sdk``) backends are supported.  Either, both, or neither
may be installed; the module degrades gracefully in all cases.

Usage::

    # Prometheus (opt-in)
    metrics = FleuveMetrics(workflow_type="order", enable_prometheus=True)

    # OpenTelemetry (opt-in)
    metrics = FleuveMetrics(workflow_type="order", enable_otel=True)

    # Both
    metrics = FleuveMetrics(workflow_type="order", enable_prometheus=True, enable_otel=True)

    metrics.record_event_processed()
    metrics.record_command_processed(status="success", latency_seconds=0.012)
    metrics.record_action_executed()
    metrics.record_action_failed(error_type="TimeoutError")
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Generator

# ---------------------------------------------------------------------------
# Prometheus backend (optional)
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter, Gauge, Histogram  # type: ignore[import-untyped]

    _PROMETHEUS_AVAILABLE: bool = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

    class Counter:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def labels(self, *args: Any, **kwargs: Any) -> Counter:
            return self

        def inc(self, amount: float = 1) -> None:
            pass

    class Gauge:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def labels(self, *args: Any, **kwargs: Any) -> Gauge:
            return self

        def set(self, value: float) -> None:
            pass

        def inc(self, amount: float = 1) -> None:
            pass

        def dec(self, amount: float = 1) -> None:
            pass

    class Histogram:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def labels(self, *args: Any, **kwargs: Any) -> Histogram:
            return self

        def observe(self, value: float) -> None:
            pass


# ---------------------------------------------------------------------------
# OpenTelemetry Metrics backend (optional)
# ---------------------------------------------------------------------------

try:
    from opentelemetry import metrics as _otel_metrics  # type: ignore[import-untyped]

    _OTEL_METRICS_AVAILABLE: bool = True
except ImportError:
    _OTEL_METRICS_AVAILABLE = False
    _otel_metrics = None  # type: ignore[assignment]


class _OtelCounterNoop:
    def add(self, amount: float = 1, attributes: dict | None = None) -> None:
        pass


class _OtelHistogramNoop:
    def record(self, amount: float, attributes: dict | None = None) -> None:
        pass


class _OtelGaugeNoop:
    def set(self, amount: float, attributes: dict | None = None) -> None:
        pass


class FleuveMetrics:
    """Metrics collector for Fleuve workflows — Prometheus and/or OpenTelemetry.

    Both backends are optional and can be enabled independently.

    Usage::

        metrics = FleuveMetrics(
            workflow_type="order",
            enable_prometheus=True,   # requires prometheus_client
            enable_otel=True,         # requires opentelemetry-sdk
        )

        metrics.record_event_processed()
        with metrics.time_command():
            ...  # timed block
        metrics.record_action_executed()
        metrics.record_action_failed("TimeoutError")
        metrics.set_active_workflows(42)
    """

    def __init__(
        self,
        workflow_type: str,
        enable_metrics: bool = True,   # kept for backward compatibility
        enable_prometheus: bool | None = None,
        enable_otel: bool = False,
    ):
        """Initialize metrics for a workflow type.

        Args:
            workflow_type: Name of the workflow type
            enable_metrics: Legacy flag; enables Prometheus if True (default: True)
            enable_prometheus: Explicitly enable/disable Prometheus metrics.
                               When None, falls back to ``enable_metrics``.
            enable_otel: Enable OpenTelemetry Metrics API (default: False)
        """
        self.workflow_type = workflow_type

        prom_flag = enable_prometheus if enable_prometheus is not None else enable_metrics
        self._prometheus_enabled = prom_flag and _PROMETHEUS_AVAILABLE
        self._otel_enabled = enable_otel and _OTEL_METRICS_AVAILABLE

        # Legacy compat attribute
        self.enabled = self._prometheus_enabled

        # ------------------------------------------------------------------
        # Prometheus metrics
        # ------------------------------------------------------------------
        if self._prometheus_enabled:
            self.events_processed = Counter(
                "fleuve_events_processed_total",
                "Total number of events processed",
                ["workflow_type"],
            )
            self.commands_processed = Counter(
                "fleuve_commands_processed_total",
                "Total number of commands processed",
                ["workflow_type", "status"],
            )
            self.command_latency = Histogram(
                "fleuve_command_latency_seconds",
                "Time taken to process a command (decide + evolve + DB write)",
                ["workflow_type"],
            )
            self.workflow_errors = Counter(
                "fleuve_workflow_errors_total",
                "Total number of workflow errors",
                ["workflow_type", "error_type"],
            )
            self.actions_executed = Counter(
                "fleuve_actions_executed_total",
                "Total number of actions executed",
                ["workflow_type"],
            )
            self.failed_actions_total = Counter(
                "fleuve_failed_actions_total",
                "Total number of actions that permanently failed after all retries",
                ["workflow_type", "error_type"],
            )
            self.action_duration = Histogram(
                "fleuve_action_duration_seconds",
                "Duration of action execution",
                ["workflow_type"],
            )
            self.state_load_time = Histogram(
                "fleuve_state_load_seconds",
                "Time taken to load/reconstruct workflow state",
                ["workflow_type"],
            )
            self.active_workflows = Gauge(
                "fleuve_active_workflows",
                "Number of active (non-cancelled, non-paused) workflows",
                ["workflow_type"],
            )
            self.pending_delays = Gauge(
                "fleuve_pending_delays",
                "Number of pending delay schedules",
                ["workflow_type"],
            )
            self.cache_hits = Counter(
                "fleuve_cache_hits_total",
                "Ephemeral state cache hits",
                ["workflow_type"],
            )
            self.cache_misses = Counter(
                "fleuve_cache_misses_total",
                "Ephemeral state cache misses",
                ["workflow_type"],
            )
            # Outbox publisher metrics (JetStream)
            self.outbox_events_published = Counter(
                "fleuve_outbox_events_published_total",
                "Events published from outbox to NATS JetStream",
                ["workflow_type"],
            )
            self.outbox_publish_failures = Counter(
                "fleuve_outbox_publish_failures_total",
                "Failed outbox publish attempts",
                ["workflow_type", "error_type"],
            )
            self.outbox_queue_depth = Gauge(
                "fleuve_outbox_queue_depth",
                "Number of unpublished events in outbox (pushed=false)",
                ["workflow_type"],
            )
            self.outbox_publish_latency = Histogram(
                "fleuve_outbox_publish_latency_seconds",
                "Time taken to publish an event to JetStream",
                ["workflow_type"],
            )
            self.outbox_batch_size = Histogram(
                "fleuve_outbox_batch_size",
                "Number of events published in a single batch",
                ["workflow_type"],
            )
            self.jetstream_consumer_lag = Gauge(
                "fleuve_jetstream_consumer_lag",
                "Lag between JetStream consumer and PostgreSQL",
                ["workflow_type", "consumer_name"],
            )
            self.jetstream_messages_consumed = Counter(
                "fleuve_jetstream_messages_consumed_total",
                "Messages consumed from JetStream",
                ["workflow_type", "consumer_name"],
            )
            self.jetstream_consumer_errors = Counter(
                "fleuve_jetstream_consumer_errors_total",
                "Errors during JetStream consumption",
                ["workflow_type", "consumer_name", "error_type"],
            )
            self.reconciliation_stuck_events = Gauge(
                "fleuve_reconciliation_stuck_events",
                "Number of events stuck in unpublished state",
                ["workflow_type"],
            )
            self.reconciliation_checks = Counter(
                "fleuve_reconciliation_checks_total",
                "Number of reconciliation checks performed",
                ["workflow_type"],
            )
            self.reader_fallback_activated = Counter(
                "fleuve_reader_fallback_activated_total",
                "Number of times PostgreSQL fallback was activated",
                ["workflow_type", "reader_name"],
            )
            self.reader_events_read = Counter(
                "fleuve_reader_events_read_total",
                "Events read by readers",
                ["workflow_type", "reader_name", "source"],
            )

        # ------------------------------------------------------------------
        # OpenTelemetry metrics
        # ------------------------------------------------------------------
        if self._otel_enabled and _otel_metrics is not None:
            _meter = _otel_metrics.get_meter("fleuve", "0.1.0")
            self._otel_events_processed = _meter.create_counter(
                "fleuve.events_processed",
                description="Total events processed",
            )
            self._otel_commands_processed = _meter.create_counter(
                "fleuve.commands_processed",
                description="Total commands processed",
            )
            self._otel_command_latency = _meter.create_histogram(
                "fleuve.command_latency",
                unit="s",
                description="Command processing latency",
            )
            self._otel_actions_executed = _meter.create_counter(
                "fleuve.actions_executed",
                description="Total actions executed",
            )
            self._otel_actions_failed = _meter.create_counter(
                "fleuve.actions_failed",
                description="Total actions permanently failed",
            )
            self._otel_action_duration = _meter.create_histogram(
                "fleuve.action_duration",
                unit="s",
                description="Action execution duration",
            )
            self._otel_state_load_time = _meter.create_histogram(
                "fleuve.state_load_time",
                unit="s",
                description="State load/reconstruction time",
            )
            self._otel_active_workflows = _meter.create_up_down_counter(
                "fleuve.active_workflows",
                description="Active workflow instances",
            )
            self._otel_pending_delays = _meter.create_up_down_counter(
                "fleuve.pending_delays",
                description="Pending delay schedules",
            )
        else:
            self._otel_events_processed = _OtelCounterNoop()
            self._otel_commands_processed = _OtelCounterNoop()
            self._otel_command_latency = _OtelHistogramNoop()
            self._otel_actions_executed = _OtelCounterNoop()
            self._otel_actions_failed = _OtelCounterNoop()
            self._otel_action_duration = _OtelHistogramNoop()
            self._otel_state_load_time = _OtelHistogramNoop()
            self._otel_active_workflows = _OtelCounterNoop()
            self._otel_pending_delays = _OtelCounterNoop()

    # ------------------------------------------------------------------
    # Core record methods
    # ------------------------------------------------------------------

    def record_event_processed(self) -> None:
        """Record that an event was processed."""
        attrs = {"workflow_type": self.workflow_type}
        if self._prometheus_enabled:
            self.events_processed.labels(workflow_type=self.workflow_type).inc()
        self._otel_events_processed.add(1, attributes=attrs)

    def record_command_processed(
        self, status: str = "success", latency_seconds: float | None = None
    ) -> None:
        """Record that a command was processed.

        Args:
            status: Command status (success, rejected, error)
            latency_seconds: Optional duration of command processing
        """
        attrs = {"workflow_type": self.workflow_type, "status": status}
        if self._prometheus_enabled:
            self.commands_processed.labels(
                workflow_type=self.workflow_type, status=status
            ).inc()
            if latency_seconds is not None:
                self.command_latency.labels(
                    workflow_type=self.workflow_type
                ).observe(latency_seconds)
        self._otel_commands_processed.add(1, attributes=attrs)
        if latency_seconds is not None:
            self._otel_command_latency.record(
                latency_seconds, attributes={"workflow_type": self.workflow_type}
            )

    @contextmanager
    def time_command(self) -> Generator[None, None, None]:
        """Context manager that times a command and records latency."""
        start = time.monotonic()
        try:
            yield
        finally:
            elapsed = time.monotonic() - start
            self.record_command_processed(status="success", latency_seconds=elapsed)

    def record_workflow_error(self, error_type: str) -> None:
        """Record a workflow error."""
        if self._prometheus_enabled:
            self.workflow_errors.labels(
                workflow_type=self.workflow_type, error_type=error_type
            ).inc()

    def record_action_executed(self, duration_seconds: float | None = None) -> None:
        """Record that an action was executed successfully.

        Args:
            duration_seconds: Optional action execution duration
        """
        attrs = {"workflow_type": self.workflow_type}
        if self._prometheus_enabled:
            self.actions_executed.labels(workflow_type=self.workflow_type).inc()
            if duration_seconds is not None:
                self.action_duration.labels(
                    workflow_type=self.workflow_type
                ).observe(duration_seconds)
        self._otel_actions_executed.add(1, attributes=attrs)
        if duration_seconds is not None:
            self._otel_action_duration.record(duration_seconds, attributes=attrs)

    def record_action_failed(self, error_type: str) -> None:
        """Record that an action permanently failed after all retries.

        Args:
            error_type: Exception class name (e.g., 'ValueError', 'ConnectionError')
        """
        attrs = {"workflow_type": self.workflow_type, "error_type": error_type}
        if self._prometheus_enabled:
            self.failed_actions_total.labels(
                workflow_type=self.workflow_type, error_type=error_type
            ).inc()
        self._otel_actions_failed.add(1, attributes=attrs)

    # Legacy alias
    def record_failed_action(self, error_type: str) -> None:
        self.record_action_failed(error_type)

    def record_state_load_time(self, duration_seconds: float) -> None:
        """Record time taken to load/reconstruct workflow state from DB/snapshot."""
        attrs = {"workflow_type": self.workflow_type}
        if self._prometheus_enabled:
            self.state_load_time.labels(
                workflow_type=self.workflow_type
            ).observe(duration_seconds)
        self._otel_state_load_time.record(duration_seconds, attributes=attrs)

    def set_active_workflows(self, count: int) -> None:
        """Update active-workflow gauge."""
        attrs = {"workflow_type": self.workflow_type}
        if self._prometheus_enabled:
            self.active_workflows.labels(workflow_type=self.workflow_type).set(count)
        # OTel UpDownCounter: just add delta; re-set not idiomatic but acceptable
        # callers should pass absolute value; we record as-is
        self._otel_active_workflows.add(0, attributes=attrs)  # no-op; gauge not directly wrappable

    def set_pending_delays(self, count: int) -> None:
        """Update pending-delay-schedules gauge."""
        attrs = {"workflow_type": self.workflow_type}
        if self._prometheus_enabled:
            self.pending_delays.labels(workflow_type=self.workflow_type).set(count)

    def record_cache_hit(self) -> None:
        """Record an ephemeral-state cache hit."""
        if self._prometheus_enabled:
            self.cache_hits.labels(workflow_type=self.workflow_type).inc()

    def record_cache_miss(self) -> None:
        """Record an ephemeral-state cache miss."""
        if self._prometheus_enabled:
            self.cache_misses.labels(workflow_type=self.workflow_type).inc()

    # ------------------------------------------------------------------
    # Outbox / JetStream methods (unchanged API)
    # ------------------------------------------------------------------

    def record_outbox_published(self, count: int = 1) -> None:
        if self._prometheus_enabled:
            self.outbox_events_published.labels(workflow_type=self.workflow_type).inc(count)

    def record_outbox_failure(self, error_type: str) -> None:
        if self._prometheus_enabled:
            self.outbox_publish_failures.labels(
                workflow_type=self.workflow_type, error_type=error_type
            ).inc()

    def set_outbox_queue_depth(self, depth: int) -> None:
        if self._prometheus_enabled:
            self.outbox_queue_depth.labels(workflow_type=self.workflow_type).set(depth)

    def observe_outbox_latency(self, latency_seconds: float) -> None:
        if self._prometheus_enabled:
            self.outbox_publish_latency.labels(
                workflow_type=self.workflow_type
            ).observe(latency_seconds)

    def observe_outbox_batch_size(self, batch_size: int) -> None:
        if self._prometheus_enabled:
            self.outbox_batch_size.labels(workflow_type=self.workflow_type).observe(batch_size)

    def set_consumer_lag(self, consumer_name: str, lag: int) -> None:
        if self._prometheus_enabled:
            self.jetstream_consumer_lag.labels(
                workflow_type=self.workflow_type, consumer_name=consumer_name
            ).set(lag)

    def record_jetstream_consumed(self, consumer_name: str, count: int = 1) -> None:
        if self._prometheus_enabled:
            self.jetstream_messages_consumed.labels(
                workflow_type=self.workflow_type, consumer_name=consumer_name
            ).inc(count)

    def record_jetstream_error(self, consumer_name: str, error_type: str) -> None:
        if self._prometheus_enabled:
            self.jetstream_consumer_errors.labels(
                workflow_type=self.workflow_type,
                consumer_name=consumer_name,
                error_type=error_type,
            ).inc()

    def set_stuck_events(self, count: int) -> None:
        if self._prometheus_enabled:
            self.reconciliation_stuck_events.labels(
                workflow_type=self.workflow_type
            ).set(count)

    def record_reconciliation_check(self) -> None:
        if self._prometheus_enabled:
            self.reconciliation_checks.labels(workflow_type=self.workflow_type).inc()

    def record_reader_fallback(self, reader_name: str) -> None:
        if self._prometheus_enabled:
            self.reader_fallback_activated.labels(
                workflow_type=self.workflow_type, reader_name=reader_name
            ).inc()

    def record_reader_event(self, reader_name: str, source: str, count: int = 1) -> None:
        if self._prometheus_enabled:
            self.reader_events_read.labels(
                workflow_type=self.workflow_type,
                reader_name=reader_name,
                source=source,
            ).inc(count)
