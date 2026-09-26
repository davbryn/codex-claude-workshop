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

python app.py                 # real Codex + Claude Code CLIs
python app.py --fake-agents   # simulated agents: no usage consumed
```

Other options:

| Option | Meaning |
| --- | --- |
| `--fake-delay 2.5` | seconds per fake-agent turn |
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
* The **Codex Output** and **Claude Output** tabs show the raw CLI output, live and clearly labelled.
  Use them to check that what an agent *says* matches what it *did*.

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
python tools/make_avatars.py    # regenerate the placeholder avatars in assets/
```

Fake agents are a small script, `workshop/agents/fake_agent.py`, launched by the
`FakeAdapter` in `workshop/agents/fake.py`. They run as real child processes, so the
tests exercise the same process handling, pausing, error handling and completion
logic as the real CLIs. Replace `assets/codex.png` and `assets/claude.png` with any
images you like. If they are missing, the app shows generated initials instead.

```
app.py                      entry point
workshop/conversation.py    conversation.md parsing, handoff detection, appending
workshop/orchestrator.py    referee state machine (Qt signals, no GUI code)
workshop/prompts.py         rules + personality + turn prompt
workshop/project.py         directory safety checks, AGENT_README.md, backups
workshop/config.py          settings.json + personalities.json
workshop/agents/            CLI adapters (codex, claude, fake) + process wrapper
workshop/ui/                main window, agent panels, dialogs, conversation view
workshop/templates/         AGENT_README.md protocol template
```
