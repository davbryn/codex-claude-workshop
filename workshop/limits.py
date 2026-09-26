"""Recognise "usage limit reached" failures in agent CLI output, and when the limit resets.

Both CLIs fail a turn when the account's usage limit is hit (Claude Code exits 1;
Codex prints an error). That is not a crash: the right response is to pause
cleanly and try again after the reset. This module only reads the turn's own
output; it never calls any service.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

LIMIT_RX = re.compile(
    r"usage limit|hit your (?:usage )?limit|limit (?:reached|exceeded)|out of (?:usage|credits)|"
    r"quota (?:exceeded|exhausted)|rate[- ]limit(?:ed)? (?:reached|exceeded)|too many requests|"
    r"\b429\b|insufficient[_ ]quota",
    re.I,
)
# Claude Code: "Claude AI usage limit reached|1790472600"
EPOCH_AFTER_BAR = re.compile(r"limit reached\|(\d{10})")
# stream-json rate_limit_event {"status":"rejected", "resetsAt":1790472600}
RESETS_AT = re.compile(r'"resetsAt"\s*:\s*(\d{10})')
# "resets 9:30pm", "resets at 21:30", "try again at 9:41 PM"
CLOCK = re.compile(r"(?:resets?|try again)(?: at| after)?\s+(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?", re.I)
# "try again in 2 hours 13 minutes", "resets in 45m"
RELATIVE = re.compile(r"in\s+(?:(\d+)\s*h(?:ours?|rs?)?)?\s*(?:(\d+)\s*m(?:in(?:ute)?s?)?)?", re.I)


@dataclass
class UsageLimit:
    agent: str
    reset_at: float | None  # epoch seconds, if the output said when
    evidence: str  # the line that showed it (shown to the user)

    def reset_text(self) -> str:
        if self.reset_at is None:
            return "an unknown time"
        return datetime.fromtimestamp(self.reset_at).strftime("%H:%M")


def _rejected_event(line: str) -> tuple[bool, float | None]:
    """A stream-json rate_limit_event that actually rejected the request."""
    if '"rate_limit_event"' not in line or '"rejected"' not in line:
        return False, None
    try:
        data = json.loads(line[line.index("{"):])
        info = data.get("rate_limit_info", {})
        if info.get("status") == "rejected":
            reset = info.get("resetsAt")
            return True, float(reset) if reset else None
    except (ValueError, AttributeError):
        pass
    m = RESETS_AT.search(line)
    return True, float(m.group(1)) if m else None


def _parse_reset(line: str, now: float) -> float | None:
    if m := EPOCH_AFTER_BAR.search(line):
        return float(m.group(1))
    if m := RESETS_AT.search(line):
        return float(m.group(1))
    if m := CLOCK.search(line):
        hour, minute, meridiem = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower().replace(".", "")
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        if 0 <= hour < 24 and 0 <= minute < 60:
            base = datetime.fromtimestamp(now)
            when = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if when.timestamp() <= now:
                when += timedelta(days=1)
            return when.timestamp()
    for m in RELATIVE.finditer(line):
        hours, minutes = m.group(1), m.group(2)
        if hours or minutes:
            return now + int(hours or 0) * 3600 + int(minutes or 0) * 60
    return None


def detect_usage_limit(agent: str, lines: list[str], now: float | None = None) -> UsageLimit | None:
    """Look through a failed turn's output for a usage-limit error. Newest evidence wins."""
    now = time.time() if now is None else now
    found: UsageLimit | None = None
    for line in lines:
        rejected, reset = _rejected_event(line)
        if rejected:
            found = UsageLimit(agent, reset or (found.reset_at if found else None), "rate limit: rejected")
            continue
        if '"rate_limit_event"' in line:
            continue  # an "allowed" status report, not an error
        if LIMIT_RX.search(line):
            text = re.sub(r"\|\d{10}\b", "", re.sub(r"\s+", " ", line)).strip()
            found = UsageLimit(agent, _parse_reset(line, now) or (found.reset_at if found else None), text[:200])
    if found and found.reset_at is not None and not (now - 60 < found.reset_at < now + 8 * 86400):
        found.reset_at = None  # nonsense timestamp: don't schedule anything on it
    return found
