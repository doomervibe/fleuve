"""OpenTelemetry tracing for Fleuve workflows.

Provides optional distributed tracing with graceful degradation when
opentelemetry-api is not installed.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

if TYPE_CHECKING:
    from opentelemetry import trace as _trace_mod
    from opentelemetry.trace import StatusCode as _StatusCode

try:
    from opentelemetry import trace  # type: ignore[import-untyped]
    from opentelemetry.trace import StatusCode  # type: ignore[import-untyped]

    _OTEL_AVAILABLE: bool = True
except ImportError:
    trace = None  # type: ignore[assignment]
    StatusCode = None  # type: ignore[assignment,misc]
    _OTEL_AVAILABLE = False


class FleuveTracer:
    """Tracer for Fleuve workflow operations.

    Creates spans for key operations. No-op when OpenTelemetry is not installed.
    """

    def __init__(self, workflow_type: str, enable: bool = True) -> None:
        self.workflow_type: str = workflow_type
        self.enabled: bool = enable and _OTEL_AVAILABLE

    @contextmanager
    def span(
        self, name: str, attributes: dict[str, Any] | None = None
    ) -> Generator[Any, None, None]:
        """Create a span; no-op if OTel is not available."""
        if not self.enabled or trace is None:
            yield None
            return

        tracer = trace.get_tracer("fleuve", "0.1.0")
        attrs: dict[str, Any] = {"fleuve.workflow_type": self.workflow_type}
        if attributes:
            attrs.update(attributes)
        with tracer.start_as_current_span(name, attributes=attrs) as span:
            try:
                yield span
            except Exception as e:
                if span is not None and StatusCode is not None:
                    span.set_status(StatusCode.ERROR, str(e))
                    span.record_exception(e)
                raise


class _NoopTracer:
    """No-op tracer when OpenTelemetry is disabled."""

    @contextmanager
    def span(
        self, name: str, attributes: dict[str, Any] | None = None
    ) -> Generator[None, None, None]:
        yield
