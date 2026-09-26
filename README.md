# Codex ↔ Claude Workshop

A local desktop app (Python + PySide6) for watching **Codex** and **Claude Code**
build a project together by taking alternating turns. They talk to each other
through one shared, human-readable `conversation.md` file in the project. The app
acts as referee.

```
conversation.md is the shared agent communication medium.
The GUI is the referee.
The source tree is the shared workspace.
```

## Install and run (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m workshop.theatre.neural_tts --download   # optional: natural voices (~340 MB, one-off)

python app.py                 # real Codex + Claude Code CLIs
python app.py --demo          # scripted Workshop Theatre demo: no setup, no usage
python app.py --demo --record demo.mp4   # render the demo to a video (needs ffmpeg)
python app.py --fake-agents   # the setup screen, with simulated agents
```

Other options:

| Option | Meaning |
| --- | --- |
| `--demo-speed 2` | play the demo faster (or slower, e.g. `0.7`) |
| `--fake-delay 1.6` | seconds per fake-agent step |
| `--project DIR --prompt "..."` | skip the setup screen and start a new conversation in `DIR` |
| `--project DIR` | skip setup and continue the existing `conversation.md` in `DIR` |
| `--first Codex\|Claude` | which agent goes first (with `--project`) |

### Requirements for real agents

* **Claude Code**: `claude` on `PATH` and logged in. Tested with `claude 2.1.282`.
* **Codex CLI**: install with `winget install OpenAI.Codex` (or `npm i -g @openai/codex`), then run
  `codex login`. Tested with `codex-cli 0.156.1`. winget may not create a `codex` alias. The adapter
  finds the winget binary automatically, and you can also set a full path under
  *Advanced: agent commands*.

## Using it

1. **Setup screen:** choose a project directory, describe what to build, and pick or edit
   personalities (presets live in `config/personalities.json`, and **Save Preset…** adds
   your own). Then choose who goes first and press **Start Workshop**.
2. The app creates `AGENT_README.md` (the shared agent protocol) if it's missing, and
   starts `conversation.md` with your prompt. It never overwrites an existing README.
   If a `conversation.md` already exists, you can **continue** it or **start new**.
   Starting new keeps a timestamped backup of the old one.
3. The first agent runs. When its process exits, the app re-reads `conversation.md`,
   finds the latest handoff, and starts the other agent.

Controls:

* **Pause:** the current turn finishes, but the next agent does not start. **Resume** continues.
* **Stop:** terminates the running agent (its whole process tree) after confirmation.
  All files and history are kept.
* **Human Turn:** appends a `## Human — Intervention` entry with your message and a
  handoff to the agent you choose. Available whenever no agent is running.
* **Open Project / Open Conversation:** open the folder or file in Explorer or your editor.
* The **Gilfoyle (Codex)** and **Dinesh (Claude)** output tabs show the raw CLI output, live and clearly labelled.
  Use them to check that what an agent *says* matches what it *did*.
* **🔊 Voices** (Ctrl+M) mutes or unmutes speech, **🔔 Sounds** toggles sound effects,
  **🎭 Theatre** (F11 / Ctrl+T) switches Theatre Mode, and **⚙ Settings** opens the settings.

## Workshop Theatre: Gilfoyle & Dinesh

The presentation layer is themed on HBO's *Silicon Valley*: **Codex plays Gilfoyle** and
**Claude plays Dinesh**, pair-programming in a cluttered hacker-house office. The agents'
real identities don't change: headings stay `## Codex — Turn N`, handoffs stay `@Claude`,
and `conversation.md` remains the source of truth. The cast is theatre on top.

**In the prompts.** Every real turn prompt carries a short character layer between the
core rules and the turn instruction (`workshop/theatre/cast.py`). It:
* states the mapping explicitly ("For the theatrical collaboration layer, you are
  GILFOYLE. The other agent, Claude, is DINESH.");
* asks the agent to read the other's turn, react to something specific, do real
  engineering, report in character and hand over;
* bans assistant and performance-review phrasing;
* describes the relationship and the "insult → claim → evidence → unbearable winner →
  grudging concession" arc;
* forbids inventing bugs for a joke;
* adds up to four **banter callbacks**, short factual notes from this session's public
  conversation (for example "Dinesh caught a Gilfoyle bug — turn 3: …"). They are
  derived deterministically (`workshop/theatre/banter.py`) and never touch technical
  state.

**Hostility** (Settings → The Cast) has five levels: Civil, Normal, Startup House,
**Gilfoyle & Dinesh** (the default) and Nuclear. Nuclear is ruder but must stay
technically productive. The cast can be switched off in the same tab.

**On stage** (all drawn procedurally, with no image assets):
* **The set:** Gilfoyle's server rack **ANTON** blinking away, a **Pied Piper**
  whiteboard ("Build / Test / Ship? / Probably", Weissman score in the corner), a
  **HACKER HOSTEL** banner, a night window with blinds, a desk lamp, energy drinks, a
  penguin, a pizza box, and a monitor each.
* **Gilfoyle** is long-haired and bearded, in glasses and a black hoodie, and
  *under-animated* on purpose. Insults get an eyebrow. When he's proven wrong his eyes
  flick. When Dinesh celebrates he slowly looks over and stares. His best smile is a
  small smirk.
* **Dinesh** wears a maroon hoodie over a striped polo and reacts to everything: he
  glares after an insult, throws his hands up in outrage, and when he catches a
  Gilfoyle bug he fist-pumps a **YES.** with the gold chain out.
* **Comic timing:** after an insult there is a short pause, the target glowers, then
  his turn starts. When Dinesh catches a bug, he grins first, Gilfoyle slowly
  side-eyes him, then Dinesh speaks. The beats are under a second each, and you can
  turn them off in Settings.
* **Speech bubbles** show the most entertaining *real* sentence of the entry. A scorer
  prefers lines that name the other agent, jab, concede or criticise over boilerplate;
  it never invents text. Gilfoyle's bubbles are dry and square; Dinesh's are rounder
  and a little tilted.
* **Captions** appear rarely: DINESH WILL NEVER LET THIS GO, THIS WILL BE MENTIONED
  AGAIN, GRUDGING CONCESSION, OWN GOAL, IMPRESSIVE. (both wrong), UNCOMFORTABLE
  AGREEMENT, CHARACTER DEVELOPMENT, TECHNICAL DISAGREEMENT. Small side labels such as
  GILFOYLE SMUG are rarer still.
* **The boss walks in:** your Human Turn stops them both. Dinesh looks worried if the
  message sounds stern; Gilfoyle looks unimpressed.
* **The finale:** confetti falls on Dinesh only. He goes for a high five, which
  Gilfoyle eventually, barely, returns. Then the card reads *PROJECT COMPLETE —
  Somehow.* with factual stats.
* **Sounds:** synthesized locally, including a "YES." sting, a sad-trombone
  concession, and a one-second grindcore blast when Gilfoyle catches Dinesh out.

**PETTY SCOREBOARD.** Bugs caught, arguments won by evidence, and grudging concessions
received are counted from the conversation only. It's part of the joke, not a model
leaderboard.

**Dashboard.** Below the stage are the scoreboard, the current status (turn, elapsed
time, test counts, who is working) and the last few raw CLI lines. Below those are the
conversation, with portraits, and the project's files. The message box at the bottom
sends a Human Turn: if an agent is working, the workshop pauses after its turn and then
delivers your message.

Everything on stage comes **only from public information**: `conversation.md` entries,
observable CLI output (tool calls, commands, test summaries) and process states. Nothing
claims to show private reasoning, and none of it can affect orchestration.

**Pacing.** A character finishes its line before the next agent is launched. The app
waits at most 25 seconds, so presentation can delay a turn slightly but never block,
skip or reorder one.

**Voices** are optional and fully local; no cloud account is needed.
* **Kokoro neural voices** (after the one-off download above):
  * Gilfoyle is *Onyx*, deep and calm, played about 12% slower.
  * Dinesh is *Puck*, lighter, about 12% faster.
  * Both can be changed in Settings.
  * Mouths follow the actual loudness of the voice.
* **Windows system voices** are the fallback. Gilfoyle is pitched lower and slower,
  Dinesh higher and quicker.
* Neither can imitate the actors. The goal is contrast.

**Their monitors are live.** Each character's monitor is angled toward him and visible
to you, and it shows what he is actually doing:
* **Real code changes:** the project folder is snapshotted when a turn starts and
  rescanned while it runs, so you see real diffs of what changed on disk, typing
  themselves out.
* **The terminal:** the commands he runs, with their output.
* **Files he's reading:** shown straight from disk (only files inside the project).
* **When idle:** he browses a fictional internet that is mostly unkind about the other
  one: Stack Underflow, Anton's status page, "is gilfoyle a real name", a gold-chain
  shop. It's set dressing and never presented as something the agents said.

**Camera cuts.** While an agent works, the stage pushes in on his monitor and shows
it full-size, rendered at the stage's own resolution so the code is readable in any
window. He stays in a live inset in the corner, with the other one in a smaller
"meanwhile" inset. The camera cuts back to the room for every spoken line, for cards,
for the boss walking in, and briefly for test results so you see the reaction. You can
turn this off in Settings → Appearance.

**Usage limits.** When Claude or Codex runs out of usage mid-turn, the workshop treats
it as a pause, not a crash. The card shows who is out and when the limit resets
(Claude reports the exact time). The workshop then resumes automatically a minute
after the reset. It tries that once; you can always press Resume yourself.

**Turn logs.** Every turn's raw CLI output is saved to
`<project>/.workshop/logs/`, so a failure can be read after the window is closed.

**Recording.** `python app.py --demo --record demo.mp4` plays the episode in Theatre
Mode and saves an MP4. The soundtrack is rebuilt from the app's own voice audio and
sound effects rather than recorded from your speakers. Add `--record-full` to include
the whole window.

**Theatre Mode** (F11) hides the header, dashboard and diagnostics and gives the stage
most of the window, which is handy on a second monitor.

**Settings** (The Cast / Appearance / Audio / Personality) are saved to
`config/settings.json`. Settings from before the cast are migrated once to the
Gilfoyle & Dinesh preset and voices.

### The demo

`python app.py --demo` plays a miniature episode in a temporary folder, using the real
orchestrator and protocol with fake agents. The project is a tiny URL shortener.
1. Dinesh builds it "properly": a storage interface, two backends, a factory and a plugin registry.
2. Gilfoyle: "There are no plugins. There will never be plugins." He deletes it down to a dict and a
   base62 counter, with a real edge-case bug in it.
3. Dinesh finds that `encode(0)` returns an empty string, so the first link is unreachable. He is
   unbearable about it, and leaves the failing test for Gilfoyle "for his growth". He also sneaks
   in an LRU cache.
4. Gilfoyle concedes, fixes the bug in one line, and immediately goes after the cache: "He cached the cache."
5. Dinesh benchmarks it to prove Gilfoyle wrong. The benchmark proves Gilfoyle right (4.6× slower). Own goal.
6. Gilfoyle asks the human a product question, and the demo answers it automatically.
7. Dinesh proposes completion. Gilfoyle reviews independently: "It was inevitable." PROJECT COMPLETE.

`--fake-agents` plays the same script.

## The protocol

Each agent entry in `conversation.md` looks like this:

```markdown
## Codex — Turn 3

**Thoughts** / **Actions** / **Result** / **Next** ...

@Claude

---
```

The referee reads **only the latest entry**:

| Latest entry ends with / contains | Result |
| --- | --- |
| `@Codex` / `@Claude` on the last line | that agent runs next |
| `HUMAN DECISION NEEDED: ...` anywhere | pauses with **⚠ HUMAN INPUT REQUIRED** |
| the line `PROJECT COMPLETE` (no handoff) | done, *if* the other agent's previous entry had the line `PROPOSE PROJECT COMPLETE` |
| no handoff, `@Bob`, both agents tagged, an agent tagging itself, or `PROJECT COMPLETE` plus a handoff | pauses and reports the problem |

Completion takes two steps. One agent adds a line `PROPOSE PROJECT COMPLETE` and hands
off. The other agent reviews independently and, if it agrees, ends with a line
`PROJECT COMPLETE`. Both markers only count as whole lines of their own, so prose such
as "the project is not complete" never triggers them. Human interventions between the
proposal and the agreement are allowed.

These rules apply equally to a turn that just finished and to a conversation opened
with **Continue existing workshop** (including one a human edited by hand).

After every agent turn the app also checks that `conversation.md` is **append-only**.
The file must still start with the entire previous conversation, and the new text must be
exactly one entry under the agent's own heading. Changes to line endings are tolerated.
If an agent edits, truncates or replaces history, adds text outside an entry, or writes
more than one entry, the workshop pauses with an error. It also saves the pre-turn
conversation as `conversation.before-<agent>-<time>.bak.md` so you can restore it.

The app also pauses and reports if an agent exits non-zero or exits without changing
`conversation.md`. The turn is never passed on silently.

**⚔ TECHNICAL DISAGREEMENT** is a purely cosmetic badge, shown when an entry contains
phrases like "I disagree" or "over-engineered". It never affects orchestration.

## Personalities

The prompt sent to an agent each turn is `CORE RULES + PERSONALITY + CURRENT TURN
INSTRUCTION` (see `workshop/prompts.py`). Personality text shapes tone only. It is never
written to `conversation.md`, and it can't override the rules, safety, turn-taking or
human instructions.

## CLI configuration

All CLI-specific code lives in `workshop/agents/`:

* `codex.py` runs `codex exec --color never --skip-git-repo-check --cd <project> <extra args> -`
  (prompt on stdin). The default extra args are
  `--sandbox workspace-write -c windows.sandbox="unelevated"`. Without the `windows.sandbox`
  setting, Codex 0.156 on Windows silently falls back to a **read-only** sandbox and can't
  edit anything.
* `claude.py` runs `claude -p --output-format stream-json --verbose <extra args>` (prompt on
  stdin). The default extra args are `--permission-mode acceptEdits --allowedTools "Bash PowerShell"`,
  which let Claude edit files and run commands (tests) without interactive prompts. The
  stream-json events are condensed into readable lines, such as `[tool] Bash: pytest -q`.

Executables and extra args can be changed on the setup screen under **Advanced: agent
commands**. They are saved to `config/settings.json`.

## Safety

This app deliberately launches coding agents that **edit files and run commands**.
Both start in the project directory you choose and are instructed to work only there,
but the actual enforcement differs:

* **Codex** runs in its CLI sandbox (`workspace-write`), which limits its writes to
  the project and temp folders and blocks network access.
* **Claude Code** starts in the project directory. Its file-edit tools follow Claude
  Code's own permission rules, but the default `--allowedTools "Bash PowerShell"` lets
  it run shell commands, and those are **not** confined to the project by the operating
  system. What it can reach depends on your local Claude Code configuration. The
  installed CLI (2.1.282) has no command-line sandbox option, so the app does not
  pretend to add one. Remove `Bash PowerShell` from its extra args if you want it
  unable to run commands at all (it then can't run tests either).

The app itself:

* warns before using a drive root, your user folder, Desktop, Documents, Downloads and similar folders;
* never runs anything as administrator;
* never performs git operations itself (the agents may choose to use git).

Use a dedicated project folder, ideally one under version control.

## Development

```powershell
python -m pytest -q
```

Fake agents are a small script, `workshop/agents/fake_agent.py`, launched by the
`FakeAdapter` in `workshop/agents/fake.py`. They run as real child processes, so the
tests exercise the same process handling, pausing, error handling and completion
logic as the real CLIs.

```
app.py                      entry point
workshop/conversation.py    conversation.md parsing, handoff detection, appending
workshop/orchestrator.py    referee state machine (Qt signals, no GUI code)
workshop/prompts.py         rules + personality + turn prompt
workshop/project.py         directory safety checks, AGENT_README.md, backups
workshop/config.py          settings.json + personalities.json
workshop/agents/            CLI adapters (codex, claude, fake) + process wrapper
workshop/theatre/           presentation logic: reactions, text excerpts, avatar states,
                            director, speech, sound effects, stats (no orchestration)
workshop/ui/                main window, stage, avatar painters, dialogs, conversation view
workshop/templates/         AGENT_README.md protocol template
```
