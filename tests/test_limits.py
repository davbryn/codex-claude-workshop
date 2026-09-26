import json
from datetime import datetime

from workshop.agents.claude import ClaudeAdapter
from workshop.limits import detect_usage_limit

NOW = datetime(2026, 9, 26, 20, 0).timestamp()


def test_claude_stream_json_limit_is_detected_with_reset():
    a = ClaudeAdapter()
    reset = int(NOW) + 5400
    events = [
        {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "resetsAt": reset}},
        {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": reset,
                                                          "rateLimitType": "five_hour"}},
        {"type": "result", "subtype": "success", "is_error": True, "num_turns": 1, "duration_ms": 800,
         "result": f"Claude AI usage limit reached|{reset}"},
    ]
    lines = [line for e in events for line in (a.format_output_line(json.dumps(e)) or "").splitlines()]
    limit = detect_usage_limit("Claude", lines, NOW)
    assert limit and limit.reset_at == reset and "|" not in limit.evidence


def test_allowed_status_and_ordinary_failures_are_not_limits():
    ok = json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "resetsAt": 1790472600}})
    assert detect_usage_limit("Claude", [ok, "Traceback (most recent call last):", "exit 1"], NOW) is None
    assert ClaudeAdapter().format_output_line(ok) is None


def test_codex_style_clock_and_relative_resets():
    clock = detect_usage_limit("Codex", ["ERROR: You've hit your usage limit. Try again at 9:41 PM."], NOW)
    assert clock and datetime.fromtimestamp(clock.reset_at).strftime("%H:%M") == "21:41"
    early = detect_usage_limit("Codex", ["You've hit your usage limit. Try again at 7:15 AM."], NOW)
    assert datetime.fromtimestamp(early.reset_at).day == 27  # tomorrow morning
    relative = detect_usage_limit("Codex", ["usage limit reached, try again in 2 hours 13 minutes"], NOW)
    assert relative.reset_at == NOW + 2 * 3600 + 13 * 60
    unknown = detect_usage_limit("Codex", ["429 Too Many Requests"], NOW)
    assert unknown and unknown.reset_at is None and unknown.reset_text() == "an unknown time"
