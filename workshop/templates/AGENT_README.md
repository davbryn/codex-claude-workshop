# Workshop Agent Protocol

This project is being built by **two AI coding agents — Codex and Claude —**
taking alternating turns, refereed by a desktop app and watched by a human.

## How turns work

1. Only the agent tagged in the latest handoff (`@Codex` or `@Claude`) acts next.
2. At the start of your turn, read `conversation.md` in full.
3. Inspect the actual code. Do not rely on the other agent's claims — verify them.
4. Make real changes during your turn: write code, fix bugs, add tests, review.
5. Test your work whenever possible and report results honestly.
6. Append your entry to the end of `conversation.md`:

   ```markdown
   ## Codex - Turn 3

   **Thoughts**
   ...

   **Actions**
   ...

   **Result**
   ...

   **Next**
   ...

   @Claude

   ---
   ```

7. End with exactly one handoff on its own line, then stop.

## Collaboration

- Disagreement is encouraged. Evidence (tests, benchmarks, running code) beats
  endless discussion.
- If the other agent was right, say so clearly.
- Humans make product decisions. If you need one, write a line beginning with
  `HUMAN DECISION NEEDED:` followed by your question. The workshop will pause.
- `conversation.md` is append-only: never modify, reformat, truncate or delete
  earlier content. The workshop checks this after every turn and pauses if the
  history changed.
- Append exactly one entry per turn, under your own heading, and never hand off
  to yourself.
- Work only inside this project directory.

## Finishing

No agent may end the project alone.

Control markers only count when they are on a line by themselves.

1. Agent A explains why it believes the work is done, adds the line
   `PROPOSE PROJECT COMPLETE`, and hands off to Agent B.
2. Agent B reviews and tests independently.
3. If B agrees, B ends its entry with the line `PROJECT COMPLETE` and **no** handoff.
   Otherwise B explains what is missing and continues working.

`PROJECT COMPLETE` is rejected unless the other agent's previous entry contained
`PROPOSE PROJECT COMPLETE`.
