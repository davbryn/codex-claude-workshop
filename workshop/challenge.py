"""The Wheel of Destiny: a challenge format for workshops.

Before the build, the wheel is spun: a skill level for each agent, the language
(only ones that can actually run on this machine) and a limitation. The rules go
into the brief and into every turn's prompt, and a checker enforces the
checkable ones after every turn, so getting caught (and the workarounds) are
real events, not scripted ones.
"""

from __future__ import annotations

import random
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .theatre.cast import CHARACTER

GIT_USR = Path(r"C:\Program Files\Git\usr\bin")
GIT_BIN = Path(r"C:\Program Files\Git\bin")


@dataclass(frozen=True)
class Slice:
    key: str
    label: str  # on the wheel
    rule: str  # what it means, for the agents
    colour: str = "#f2c94c"


SKILLS = [
    Slice("intern", "Intern, Day One", "You code like it's your first day: only the most basic constructs, a comment on nearly "
          "every line explaining it to yourself, and a nervous question in a comment now and then. It must still work.", "#7bd88f"),
    Slice("rockstar", "10x Rockstar Ninja", "As few lines as humanly possible. Clever one-liners, no comments, and you brag "
          "about line counts in your entries.", "#e0564b"),
    Slice("architect", "Enterprise Architect", "Everything behind an interface or a factory, a config for anything "
          "configurable, and you must justify every abstraction in your entry.", "#6f9dff"),
    Slice("cobol", "Retired COBOL Wizard", "Names in SHOUTING_SNAKE_CASE, numbered 'paragraph' comments above each "
          "section, and a nostalgic complaint about modern languages in every entry.", "#c9b8ff"),
    Slice("friday", "Friday, 4:55pm", "The minimum that works. You leave honest TODOs for everything else and you want "
          "to go home.", "#f2994a"),
    Slice("golfer", "Code Golfer", "Fewest characters wins. Short names, dense code; report your character count in "
          "every entry.", "#56ccf2"),
    Slice("paranoid", "Paranoid Security Engineer", "Validate everything, trust nothing, threat-model the tiniest "
          "feature, and say what you're defending against in your entry.", "#eb5757"),
    Slice("docs", "Documentation Maximalist", "Every function gets a doc comment longer than the function itself.",
          "#bb6bd9"),
]

# (key, label, how to run it, file extensions, comment syntax, needs)
LANGUAGES = [
    ("python", "Python", "python <file>.py", (".py",), "#", "python"),
    ("powershell", "PowerShell", "powershell -NoProfile -File <file>.ps1", (".ps1",), "#", "powershell"),
    ("perl", "Perl", r'"C:\Program Files\Git\usr\bin\perl.exe" <file>.pl', (".pl", ".pm", ".t"), "#", "perl"),
    ("bash", "Bash", r'"C:\Program Files\Git\bin\bash.exe" <file>.sh', (".sh",), "#", "bash"),
    ("awk", "awk (yes, awk)", r'"C:\Program Files\Git\usr\bin\awk.exe" -f <file>.awk', (".awk",), "#", "awk"),
    ("jscript", "JScript, 1996 edition", "cscript //nologo <file>.js", (".js", ".wsf"), "//", "cscript"),
    ("vbscript", "VBScript", "cscript //nologo <file>.vbs", (".vbs",), "'", "cscript"),
    ("batch", "Windows Batch", "cmd /c <file>.bat", (".bat", ".cmd"), "rem", "cmd"),
    ("fsharp", "F# script", "dotnet fsi <file>.fsx", (".fsx", ".fs"), "//", "dotnet"),
]
LANGUAGE_COLOURS = ["#4b8bbe", "#2d5d9f", "#39457e", "#4eaa25", "#9b59b6", "#f7df1e", "#945db7", "#6d6d6d", "#378bba"]

LIMITS = [
    Slice("no_loops", "No Loops", "No for, while, do, foreach or until anywhere in the code. Recursion, "
          "higher-order functions and other workarounds are fair game.", "#e0564b"),
    Slice("no_if", "No If Statements", "No if, else, elif, switch or case keywords anywhere in the code. Find another way "
          "to decide things.", "#f2994a"),
    Slice("no_digits", "No Digits", "No digit characters 0-9 anywhere in any source file, comments included. "
          "Numbers must be conjured some other way.", "#56ccf2"),
    Slice("no_vowels", "No Vowels In Names", "Every name you define (functions, variables, parameters, classes) "
          "contains no vowels (a e i o u).", "#7bd88f"),
    Slice("short_lines", "40 Columns Max", "No line of code longer than 40 characters. Anywhere.", "#c9b8ff"),
    Slice("rhyme", "Comments Must Rhyme", "Comments come in rhyming couplets: each comment line rhymes with the one "
          "before it. At least one couplet per function.", "#f2c94c"),
    Slice("shouting", "ALL STRINGS IN CAPS", "Every string literal in the code is in capital letters, including "
          "everything the program prints.", "#eb5757"),
    Slice("tiny", "100 Lines Total", "The whole project, tests included, is at most 100 lines of code.", "#bb6bd9"),
    Slice("no_imports", "No Imports", "No import, using, require, use or dot-sourcing. Standard library included. "
          "Build what you need.", "#6f9dff"),
]

JARED = [  # management's mid-build feature requests (Jared means well)
    Slice("jared:blockchain", "Put It On The Blockchain", "Jared read an article. Every change the program makes must "
          "be recorded in a tamper-evident chain: each record carries a checksum of the previous one. No libraries "
          "beyond what the rules already allow.", "#f2994a"),
    Slice("jared:klingon", "Klingon Mode", "Jared's nephew is into Klingon. Add a Klingon mode (a flag or option) that "
          "translates every message the program prints. Honourable approximations are fine.", "#eb5757"),
    Slice("jared:mascot", "A Mascot", "Jared wants the product to have a face. The program greets the user with an ASCII "
          "art mascot and the mascot reacts to how things are going.", "#7bd88f"),
    Slice("jared:easter", "An Easter Egg", "Jared wants delight. Hide an easter egg in the program: a secret input that "
          "does something surprising and wholesome. Document how to find it in DEMO.md.", "#bb6bd9"),
    Slice("jared:accessible", "Screen-Reader Friendly", "Jared attended a talk. Every screen of output must also make "
          "sense read aloud: no meaning carried only by symbols, spacing or colour.", "#56ccf2"),
]
SWAP = Slice("swap", "SKILL SWAP", "Gilfoyle and Dinesh swap skill levels for the rest of the build.", "#ffffff")

PROJECTS = [  # (label on the wheel, the brief)
    ("Habit Tracker", "a command-line habit tracker: add habits, check them off for today, show current and best "
                      "streaks; data in a file"),
    ("To-Do List", "a command-line to-do list with priorities and due dates; data in a file"),
    ("Bill Splitter", "a tip calculator and bill splitter for a group dinner"),
    ("Hangman", "a command-line Hangman game against the computer"),
    ("Roman Numerals", "a Roman numeral converter (both ways) with a small command-line interface"),
    ("Table Formatter", "a Markdown table formatter: reads a messy table, prints it neatly aligned"),
    ("Pomodoro Timer", "a command-line pomodoro timer that logs completed sessions to a file"),
    ("Word Counter", "a word-frequency counter for a text file that prints the top N words"),
]


def available_languages() -> list[tuple]:
    def have(need: str) -> bool:
        if need == "perl":
            return (GIT_USR / "perl.exe").exists()
        if need == "awk":
            return (GIT_USR / "awk.exe").exists()
        if need == "bash":
            return (GIT_BIN / "bash.exe").exists()
        if need == "cmd":
            return shutil.which("cmd") is not None
        return shutil.which(need) is not None

    return [lang for lang in LANGUAGES if have(lang[5])]


def language_slices() -> list[Slice]:
    langs = available_languages()
    return [Slice(k, label, f"Everything is written in {label.split(',')[0].split(' (')[0]} and runs with: {run}",
                  LANGUAGE_COLOURS[i % len(LANGUAGE_COLOURS)])
            for i, (k, label, run, _ext, _c, _n) in enumerate(langs)]


@dataclass
class Spin:
    wheel: str  # skill | language | limit | project
    who: str | None  # agent, for a skill spin
    slices: list[Slice]
    result: int
    near_misses: list[int] = field(default_factory=list)  # slices it almost stopped on (for the animation)

    @property
    def slice(self) -> Slice:
        return self.slices[self.result]

    def as_event(self) -> dict:
        return {"wheel": self.wheel, "who": self.who, "result": self.result, "near_misses": self.near_misses,
                "slices": [{"key": s.key, "label": s.label, "rule": s.rule, "colour": s.colour} for s in self.slices]}


def spin_all(rng: random.Random | None = None, project: bool = False) -> list[Spin]:
    rng = rng or random.Random()

    def spin(wheel, who, slices):
        result = rng.randrange(len(slices))
        misses = rng.sample([i for i in range(len(slices)) if i != result], k=min(2, len(slices) - 1))
        return Spin(wheel, who, slices, result, misses)

    spins = []
    if project:
        spins.append(spin("project", None, [Slice(f"p{i}", label, brief, LANGUAGE_COLOURS[i % len(LANGUAGE_COLOURS)])
                                            for i, (label, brief) in enumerate(PROJECTS)]))
    spins.append(spin("skill", "Codex", SKILLS))
    spins.append(spin("skill", "Claude", SKILLS))
    spins.append(spin("language", None, language_slices()))
    lang = spins[-1].slice.key
    # the whole wheel is shown, but a limitation that costs nothing in this language can't win
    allowed = [i for i, x in enumerate(LIMITS) if not trivial(x.key, lang)]
    result = rng.choice(allowed)
    misses = rng.sample([i for i in range(len(LIMITS)) if i != result], k=2)
    spins.append(Spin("limit", None, LIMITS, result, misses))
    return spins


def trivial(limit: str, language: str) -> bool:
    """Limitations that cost nothing in a language (Batch and awk have nothing to import)."""
    return limit == "no_imports" and language in ("batch", "awk")


def twist_slices(spins: list[Spin]) -> list[Slice]:
    """The Twist Wheel: a second limitation, one of Jared's feature requests, or a skill swap."""
    taken = {s.slice.key for s in spins if s.wheel in ("limit", "twist")}
    lang = next((s.slice.key for s in spins if s.wheel == "language"), "")
    limits = [x for x in LIMITS if x.key not in taken and not trivial(x.key, lang)]
    extra = [Slice("limit:" + x.key, x.label, x.rule, x.colour) for x in limits[:4]]
    return extra + JARED + [SWAP]


def spin_twist(spins: list[Spin], rng: random.Random | None = None) -> Spin:
    rng = rng or random.Random()
    slices = twist_slices(spins)
    result = rng.randrange(len(slices))
    misses = rng.sample([i for i in range(len(slices)) if i != result], k=min(2, len(slices) - 1))
    return Spin("twist", None, slices, result, misses)


def limit_keys(spins) -> list[str]:
    """Every limitation in force: the original one and any added by a twist."""
    spins = [x.as_event() if isinstance(x, Spin) else x for x in spins]
    keys = []
    for x in spins:
        key = x["slices"][x["result"]]["key"]
        if x["wheel"] == "limit":
            keys.append(key)
        elif x["wheel"] == "twist" and key.startswith("limit:"):
            keys.append(key.split(":", 1)[1])
    return keys


def skills(spins: list[Spin]) -> dict[str, Slice]:
    """Each agent's skill level, after any swap."""
    by = {x.who: x.slice for x in spins if x.wheel == "skill"}
    if any(x.wheel == "twist" and x.slice.key == "swap" for x in spins):
        by = {"Codex": by.get("Claude"), "Claude": by.get("Codex")}
    return by


def rules_text(spins: list[Spin]) -> str:
    by = {(s.wheel, s.who): s.slice for s in spins}
    lang = by[("language", None)]
    limit = by[("limit", None)]
    skill = skills(spins)
    rows = [
        "THE WHEEL OF DESTINY HAS SPOKEN. These are the rules for this build:",
        f"- LANGUAGE: {lang.label}. {lang.rule}. No other languages, tests included.",
        f"- LIMITATION: {limit.label}. {limit.rule}",
    ]
    for twist in (x for x in spins if x.wheel == "twist"):
        t = twist.slice
        if t.key.startswith("limit:"):
            rows.append(f"- TWIST, SECOND LIMITATION (from now on): {t.label}. {t.rule}")
        elif t.key.startswith("jared:"):
            rows.append(f"- TWIST, JARED'S FEATURE REQUEST (mandatory, must be done before completion): {t.label}. "
                        f"{t.rule}")
        elif t.key == "swap":
            rows.append("- TWIST: SKILL SWAP. Your skill levels have been swapped for the rest of the build.")
    rows += [
        f"- Gilfoyle (Codex) SKILL LEVEL: {skill['Codex'].label}. {skill['Codex'].rule}",
        f"- Dinesh (Claude) SKILL LEVEL: {skill['Claude'].label}. {skill['Claude'].rule}",
        "- The rules are checked automatically after every turn. Violations are reported to both of you.",
        "- Clever workarounds are encouraged. When the rules force one, say what you did in your entry.",
        "- Before proposing completion, write DEMO.md: a short, REAL terminal session (commands you actually ran and "
        "their exact output) that shows the finished program working.",
    ]
    return "\n".join(rows)


def brief(project_brief: str, spins: list[Spin]) -> str:
    project = next((s.slice.rule for s in spins if s.wheel == "project"), None)
    text = project_brief.strip() or f"Build {project}. Keep it small and tested."
    return f"{text}\n\n{rules_text(spins)}"


# -- the checker -----------------------------------------------------------------------------

@dataclass
class Violation:
    rule: str
    path: str
    line: int
    text: str

    def as_dict(self) -> dict:
        return {"rule": self.rule, "path": self.path, "line": self.line, "text": self.text[:160]}


_KEYWORDS = {
    "no_loops": r"\b(?:for|foreach|while|do|until|loop)\b|%\s*\{|ForEach-Object",
    "no_if": r"\b(?:if|else|elif|elsif|elseif|switch|case|select\s+case|unless|when)\b",
    "no_imports": r"^\s*(?:import|from\s+\S+\s+import|using|require|use|open|#r|#load|\.\s+\S+\.ps1|Import-Module)\b",
}
_DEF_NAMES = re.compile(
    r"\b(?:def|function|sub|let|let\s+mutable|var|const|class|Dim|Function|Sub)\s+([A-Za-z_]\w*)"
    r"|^\s*\$?([A-Za-z_]\w*)\s*=(?!=)|\bset\s+\"?([A-Za-z_]\w*)=", re.M)
_STRING = re.compile(r"\"((?:[^\"\\\n]|\\.)*)\"|'((?:[^'\\\n]|\\.)*)'")
IGNORE_DIRS = {".git", ".workshop", "__pycache__", "bin", "obj", ".venv", "node_modules"}


def _code_files(project: Path, exts: tuple[str, ...]) -> list[Path]:
    out = []
    for path in sorted(project.rglob("*")):
        if path.is_file() and path.suffix.lower() in exts and not (set(path.relative_to(project).parts) & IGNORE_DIRS):
            out.append(path)
    return out[:200]


def _strip_comment(line: str, comment: str) -> tuple[str, str]:
    """(code, comment) for one line, ignoring comment markers inside strings (roughly)."""
    if comment == "rem":
        m = re.match(r"\s*(?:rem\b|::)(.*)", line, re.I)
        return ("", m.group(1)) if m else (line, "")
    in_str = None
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in "\"'" and comment != "'":
            in_str = ch
        elif ch == '"' and comment == "'":
            in_str = ch
        elif line.startswith(comment, i):
            return line[:i], line[i + len(comment):]
        i += 1
    return line, ""


def _rhymes(a: str, b: str) -> bool:
    wa = re.findall(r"[a-z]+", a.lower())
    wb = re.findall(r"[a-z]+", b.lower())
    if not wa or not wb:
        return False
    x, y = wa[-1], wb[-1]
    return x == y or x[-2:] == y[-2:] or (len(x) > 2 and len(y) > 2 and x[-3:] == y[-3:])


def _check_couplets(rel: str, comments: list[tuple[int, str, str]]) -> list[Violation]:
    """Consecutive comment lines are read in pairs; each pair must rhyme, and none may be left single."""
    out, run = [], []
    for item in comments + [(-9, "", "")]:
        if run and item[0] != run[-1][0] + 1:
            for i in range(0, len(run), 2):
                pair = run[i:i + 2]
                if len(pair) == 1 or not _rhymes(pair[0][1], pair[1][1]):
                    out.append(Violation("rhyme", rel, pair[-1][0], pair[-1][2]))
            run = []
        run.append(item)
    return out


def check(project_dir: Path, spins: list[Spin] | list[dict]) -> list[Violation]:
    """Check the project's code against every limitation in force (and the language). Checkable rules only."""
    spins = [s.as_event() if isinstance(s, Spin) else s for s in spins]
    lang_key = next(s["slices"][s["result"]]["key"] for s in spins if s["wheel"] == "language")
    limits = limit_keys(spins)
    lang = next(lang for lang in LANGUAGES if lang[0] == lang_key)
    exts, comment = lang[3], lang[4]
    flags = re.I if lang_key in ("vbscript", "batch", "powershell") else 0
    project = Path(project_dir)
    found: list[Violation] = []
    # the language rule: code in other languages doesn't count as a workaround
    other = {e for L in LANGUAGES for e in L[3]} - set(exts)
    for path in _code_files(project, tuple(other)):
        found.append(Violation("wrong language", path.relative_to(project).as_posix(), 1, path.name))
    total = 0
    for path in _code_files(project, exts):
        rel = path.relative_to(project).as_posix()
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError:
            continue
        comments: list[tuple[int, str, str]] = []
        for n, raw in enumerate(lines, 1):
            code, note = _strip_comment(raw, comment)
            if raw.strip():
                total += 1
            for limit in limits:
                if _breaks(limit, raw, code, flags):
                    found.append(Violation(limit, rel, n, raw.strip()))
                    break
            if "rhyme" in limits and note.strip():
                comments.append((n, note, raw.strip()))
        if "rhyme" in limits:
            found.extend(_check_couplets(rel, comments))
    if "tiny" in limits and total > 100:
        found.append(Violation("tiny", "(whole project)", 0, f"{total} lines of code"))
    return found[:60]


def _breaks(limit: str, raw: str, code: str, flags: int) -> bool:
    """Does this line break ``limit``? (Rhyme and the total line count are checked per file / per project.)"""
    code_nostr = _STRING.sub('""', code)
    if limit in _KEYWORDS:
        return bool(re.search(_KEYWORDS[limit], code_nostr, flags))
    if limit == "no_digits":
        return bool(re.search(r"[0-9]", raw))
    if limit == "short_lines":
        return len(raw.rstrip()) > 40
    if limit == "shouting":
        for m in _STRING.finditer(code):
            text = m.group(1) if m.group(1) is not None else m.group(2)
            if text and text != text.upper():
                return True
        return False
    if limit == "no_vowels":
        for m in _DEF_NAMES.finditer(code):
            name = next(g for g in m.groups() if g)
            if re.search(r"[aeiouAEIOU]", name) and name not in ("self", "args", "main", "__init__", "__name__"):
                return True
    return False


def report(violations: list[Violation], spins) -> str:
    """The checker's report, for the next turn's prompt."""
    if not violations:
        return "RULES CHECK after the last turn: clean. No violations."
    rows = [f"RULES CHECK after the last turn: {len(violations)} violation(s). Fix them (or find a legal workaround):"]
    for v in violations[:12]:
        where = f"{v.path}:{v.line}" if v.line else v.path
        rows.append(f"  - [{v.rule}] {where}: {v.text}")
    if len(violations) > 12:
        rows.append(f"  - …and {len(violations) - 12} more")
    return "\n".join(rows)


REACTION_PROMPT = """You are {me} (the {agent} agent, playing {me} from HBO's Silicon Valley). Before a coding challenge
with {other}, the Wheel of Destiny was just spun. Here are the results, in order:
{results}

React to each spin in character, out loud, as it lands: one short line each (under 90 characters), aimed at the wheel,
the rules or {other}. Be specific to what landed. Swearing like the show is fine (ass, damn, hell, shit); no slurs.
Reply with ONLY a JSON object mapping each spin number to your line, e.g. {{"1": "...", "2": "..."}}. Do not use tools."""


def reaction_prompt(agent: str, spins: list[Spin]) -> str:
    other = "Claude" if agent == "Codex" else "Codex"
    rows = []
    for i, s in enumerate(spins, 1):
        what = f"skill level for {CHARACTER[s.who]}" if s.wheel == "skill" else {
            "language": "the language", "limit": "the limitation", "project": "the project",
            "twist": "THE TWIST WHEEL, spun halfway through the build"}[s.wheel]
        rows.append(f"{i}. {what}: {s.slice.label} ({s.slice.rule})")
    return REACTION_PROMPT.format(me=CHARACTER[agent], agent=agent, other=CHARACTER[other], results="\n".join(rows))
