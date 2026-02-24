"""Prometheus metrics for Fleuve workflows and JetStream integration.

This module provides comprehensive observability for the Fleuve framework,
including metrics for:
- Workflow event processing
- JetStream outbox publisher performance
- Event consumption and lag
- System health and errors
"""

from __future__ import annotations

from typing import Any

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


class FleuveMetrics:
    """Metrics collector for Fleuve workflows and JetStream integration.

    Provides Prometheus-compatible metrics for monitoring workflow execution,
    event processing, and JetStream outbox patterns.

    Usage:
        metrics = FleuveMetrics(workflow_type="order", enable_metrics=True)

        # Record event processing
        metrics.events_processed.labels(workflow_type="order").inc()

        # Record outbox publish
        metrics.outbox_events_published.labels(workflow_type="order").inc()

        # Update queue depth
        metrics.outbox_queue_depth.labels(workflow_type="order").set(100)
    """

    def __init__(self, workflow_type: str, enable_metrics: bool = True):
        """Initialize metrics for a workflow type.

        Args:
            workflow_type: Name of the workflow type
            enable_metrics: Whether to enable Prometheus metrics (default: True)
        """
        self.workflow_type = workflow_type
        self.enabled = enable_metrics and _PROMETHEUS_AVAILABLE

        if not self.enabled:
            return

        # Core workflow metrics
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

        self.workflow_errors = Counter(
            "fleuve_workflow_errors_total",
            "Total number of workflow errors",
            ["workflow_type", "error_type"],
        )

        self.failed_actions_total = Counter(
            "fleuve_failed_actions_total",
            "Total number of actions that permanently failed after all retries",
            ["workflow_type", "error_type"],
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

        # JetStream consumer metrics
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

        # Reconciliation metrics
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

        # Reader metrics
        self.reader_fallback_activated = Counter(
            "fleuve_reader_fallback_activated_total",
            "Number of times PostgreSQL fallback was activated",
            ["workflow_type", "reader_name"],
        )

        self.reader_events_read = Counter(
            "fleuve_reader_events_read_total",
            "Events read by readers",
            ["workflow_type", "reader_name", "source"],  # source: jetstream or postgres
        )

    def record_event_processed(self):
        """Record that an event was processed."""
        if self.enabled:
            self.events_processed.labels(workflow_type=self.workflow_type).inc()

    def record_command_processed(self, status: str = "success"):
        """Record that a command was processed.

        Args:
            status: Command status (success, rejected, error)
        """
        if self.enabled:
            self.commands_processed.labels(
                workflow_type=self.workflow_type, status=status
            ).inc()

    def record_workflow_error(self, error_type: str):
        """Record a workflow error.

        Args:
            error_type: Type of error (e.g., 'decide', 'evolve', 'subscription')
        """
        if self.enabled:
            self.workflow_errors.labels(
                workflow_type=self.workflow_type, error_type=error_type
            ).inc()

    def record_failed_action(self, error_type: str):
        """Record that an action permanently failed after all retries.

        Args:
            error_type: Exception class name (e.g., 'ValueError', 'ConnectionError')
        """
        if self.enabled:
            self.failed_actions_total.labels(
                workflow_type=self.workflow_type, error_type=error_type
            ).inc()

    def record_outbox_published(self, count: int = 1):
        """Record events published from outbox to JetStream.

        Args:
            count: Number of events published
        """
        if self.enabled:
            self.outbox_events_published.labels(workflow_type=self.workflow_type).inc(
                count
            )

    def record_outbox_failure(self, error_type: str):
        """Record an outbox publish failure.

        Args:
            error_type: Type of error (e.g., 'connection', 'timeout', 'validation')
        """
        if self.enabled:
            self.outbox_publish_failures.labels(
                workflow_type=self.workflow_type, error_type=error_type
            ).inc()

    def set_outbox_queue_depth(self, depth: int):
        """Update the outbox queue depth gauge.

        Args:
            depth: Current number of unpublished events
        """
        if self.enabled:
            self.outbox_queue_depth.labels(workflow_type=self.workflow_type).set(depth)

    def observe_outbox_latency(self, latency_seconds: float):
        """Record outbox publish latency.

        Args:
            latency_seconds: Time taken to publish an event in seconds
        """
        if self.enabled:
            self.outbox_publish_latency.labels(
                workflow_type=self.workflow_type
            ).observe(latency_seconds)

    def observe_outbox_batch_size(self, batch_size: int):
        """Record outbox batch size.

        Args:
            batch_size: Number of events in the batch
        """
        if self.enabled:
            self.outbox_batch_size.labels(workflow_type=self.workflow_type).observe(
                batch_size
            )

    def set_consumer_lag(self, consumer_name: str, lag: int):
        """Update JetStream consumer lag.

        Args:
            consumer_name: Name of the consumer
            lag: Number of events behind
        """
        if self.enabled:
            self.jetstream_consumer_lag.labels(
                workflow_type=self.workflow_type, consumer_name=consumer_name
            ).set(lag)

    def record_jetstream_consumed(self, consumer_name: str, count: int = 1):
        """Record messages consumed from JetStream.

        Args:
            consumer_name: Name of the consumer
            count: Number of messages consumed
        """
        if self.enabled:
            self.jetstream_messages_consumed.labels(
                workflow_type=self.workflow_type, consumer_name=consumer_name
            ).inc(count)

    def record_jetstream_error(self, consumer_name: str, error_type: str):
        """Record a JetStream consumer error.

        Args:
            consumer_name: Name of the consumer
            error_type: Type of error
        """
        if self.enabled:
            self.jetstream_consumer_errors.labels(
                workflow_type=self.workflow_type,
                consumer_name=consumer_name,
                error_type=error_type,
            ).inc()

    def set_stuck_events(self, count: int):
        """Update stuck events gauge.

        Args:
            count: Number of stuck unpublished events
        """
        if self.enabled:
            self.reconciliation_stuck_events.labels(
                workflow_type=self.workflow_type
            ).set(count)

    def record_reconciliation_check(self):
        """Record a reconciliation check."""
        if self.enabled:
            self.reconciliation_checks.labels(workflow_type=self.workflow_type).inc()

    def record_reader_fallback(self, reader_name: str):
        """Record that a reader activated PostgreSQL fallback.

        Args:
            reader_name: Name of the reader
        """
        if self.enabled:
            self.reader_fallback_activated.labels(
                workflow_type=self.workflow_type, reader_name=reader_name
            ).inc()

    def record_reader_event(self, reader_name: str, source: str, count: int = 1):
        """Record events read by a reader.

        Args:
            reader_name: Name of the reader
            source: Source of events ('jetstream' or 'postgres')
            count: Number of events read
        """
        if self.enabled:
            self.reader_events_read.labels(
                workflow_type=self.workflow_type,
                reader_name=reader_name,
                source=source,
            ).inc(count)
