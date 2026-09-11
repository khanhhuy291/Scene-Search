"""In-memory APM Trace Recorder for tracking fine-grained execution spans of the Search & Chat AI pipeline."""

from __future__ import annotations

import collections
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class TraceSpan:
    name: str
    category: str  # "parser" | "llm" | "embedding" | "vectordb" | "cache" | "rerank" | "chat"
    start_offset_ms: float
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionTrace:
    id: str
    timestamp: str
    query: str
    type: str  # "search" | "chat"
    route: str  # "fast_path" | "agentic_path" | "reject_ood"
    status: str  # "ok" | "fallback_429" | "error" | "degraded"
    total_duration_ms: float
    spans: list[TraceSpan] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TraceContext:
    """Thread-safe context manager for recording sub-spans within a single request trace."""

    def __init__(
        self, trace_id: str, query: str, trace_type: str = "search", route: str = "fast_path"
    ) -> None:
        self.trace_id = trace_id
        self.query = query
        self.trace_type = trace_type
        self.route = route
        self.status = "ok"
        self.start_time = time.perf_counter()
        self.spans: list[TraceSpan] = []
        self.metrics: dict[str, Any] = {}

    @contextmanager
    def span(
        self, name: str, category: str, details: dict[str, Any] | None = None
    ) -> Generator[dict[str, Any], None, None]:
        span_start = time.perf_counter()
        start_offset_ms = max(0.0, (span_start - self.start_time) * 1000)
        span_details = details.copy() if details else {}
        try:
            yield span_details
        finally:
            duration_ms = max(0.01, (time.perf_counter() - span_start) * 1000)
            self.spans.append(
                TraceSpan(
                    name=name,
                    category=category,
                    start_offset_ms=round(start_offset_ms, 2),
                    duration_ms=round(duration_ms, 2),
                    details=span_details,
                )
            )

    def record_metric(self, key: str, value: Any) -> None:
        self.metrics[key] = value

    def finish(self, status: str = "ok") -> ExecutionTrace:
        total_duration_ms = max(0.1, (time.perf_counter() - self.start_time) * 1000)
        self.status = status
        return ExecutionTrace(
            id=self.trace_id,
            timestamp=datetime.now(UTC).isoformat(),
            query=self.query,
            type=self.trace_type,
            route=self.route,
            status=self.status,
            total_duration_ms=round(total_duration_ms, 2),
            spans=self.spans,
            metrics=self.metrics,
        )


class SystemTraceRecorder:
    """Singleton in-memory circular buffer for storing and serving recent execution traces."""

    def __init__(self, maxlen: int = 100) -> None:
        self._buffer: collections.deque[ExecutionTrace] = collections.deque(maxlen=maxlen)

    def create_context(
        self, query: str, trace_type: str = "search", route: str = "fast_path"
    ) -> TraceContext:
        trace_id = f"tr-{uuid.uuid4().hex[:10]}"
        return TraceContext(trace_id=trace_id, query=query, trace_type=trace_type, route=route)

    def record(self, trace: ExecutionTrace) -> None:
        self._buffer.appendleft(trace)

    def get_recent(self, limit: int = 50, trace_type: str | None = None) -> list[dict[str, Any]]:
        results = []
        for t in self._buffer:
            if trace_type and t.type != trace_type:
                continue
            results.append(t.to_dict())
            if len(results) >= limit:
                break
        return results

    def get_by_id(self, trace_id: str) -> dict[str, Any] | None:
        for t in self._buffer:
            if t.id == trace_id:
                return t.to_dict()
        return None

    def clear(self) -> None:
        self._buffer.clear()

    def get_summary_stats(self) -> dict[str, Any]:
        count = len(self._buffer)
        if count == 0:
            return {
                "total_traces": 0,
                "avg_latency_ms": 0.0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "error_rate_pct": 0.0,
            }

        latencies = sorted([t.total_duration_ms for t in self._buffer])
        avg_lat = sum(latencies) / count
        p50 = latencies[int(count * 0.50)]
        p95 = latencies[min(count - 1, int(count * 0.95))]
        errors = sum(1 for t in self._buffer if t.status in ("error", "fallback_429"))
        error_rate = (errors / count) * 100

        return {
            "total_traces": count,
            "avg_latency_ms": round(avg_lat, 2),
            "p50_latency_ms": round(p50, 2),
            "p95_latency_ms": round(p95, 2),
            "error_rate_pct": round(error_rate, 1),
        }


_tracer: SystemTraceRecorder | None = None


def get_tracer() -> SystemTraceRecorder:
    global _tracer
    if _tracer is None:
        _tracer = SystemTraceRecorder(maxlen=100)
    return _tracer
