from core.tracer import SystemTraceRecorder


def test_trace_recorder_lifecycle():
    recorder = SystemTraceRecorder(maxlen=10)
    ctx = recorder.create_context(query="xe vàng và đèn đỏ", trace_type="search")

    with ctx.span("1. Parser", category="parser", details={"tokens": 3}) as s:
        s["embedding_text"] = "car yellow and red traffic light"

    with ctx.span("2. LLM HyDE", category="llm", details={"model": "kimi-k3"}):
        pass

    trace = ctx.finish(status="ok")
    assert trace.query == "xe vàng và đèn đỏ"
    assert trace.status == "ok"
    assert len(trace.spans) == 2
    assert trace.spans[0].category == "parser"
    assert trace.spans[0].details["embedding_text"] == "car yellow and red traffic light"
    assert trace.spans[1].category == "llm"

    recorder.record(trace)
    recent = recorder.get_recent(limit=5)
    assert len(recent) == 1
    assert recent[0]["id"] == trace.id

    stats = recorder.get_summary_stats()
    assert stats["total_traces"] == 1
    assert stats["error_rate_pct"] == 0.0
