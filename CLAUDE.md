# Newsloader — daily personalized arXiv digest to Telegram (CV project: deployment, CI eval, tracing, cost control)

## Stack & commands
- run: `uv run newsloader digest`
- test: `uv run pytest`
- lint: `uv run ruff check --fix && uv run ruff format`

## Layout
| folder | holds |
|---|---|
| src/newsloader/ | package: sources, rank, llm, store, telegram |
| tests/ | pytest |
| evals/ | frozen fixture, labels, baseline.json |
| config/ | users/<name>.yaml (per-user profiles), settings |
| docs/ | decisions.md (design decisions D1–D14) |
| .github/workflows/ | CI + deploy |

## Rules for this project
- Verify: run `uv run pytest` and show the output before reporting done.
- Paid API / LLM steps: run on 1–3 items first, check output, then scale.
- Design decisions live in `docs/decisions.md`; update it when one changes.
- Add deps with `uv add`, never pip.

## Model routing
Lowest capable model. $0 script first. Global `~/.claude/CLAUDE.md` holds the basis; keep this table in sync.

| Piece | Model |
|---|---|
| Mechanical, fully specified edits, renames, boilerplate, sweeps | deepseek-flash (`ds`) |
| Specified feature / port WITH an auto-check (tests, build, typecheck) | deepseek-flash; check fails twice → Sonnet |
| Needs session tools (MCP, browser, skills, images) | Haiku |
| Implementation, refactors, judgment | Sonnet |
| Hard bug, hard algorithm, big new system, second opinion | Opus agent |
| Planning, architecture, review | Opus inline, not the doer |
Run them side by side: launch every independent piece in one message (`ds` in background + agents);
pipeline spec → fill → review per piece instead of waiting for the whole batch. Wait only on a real dependency.

## Mistakes
Logged in `.claude/MEMORY.md`, auto-loaded each session. When I flag a mistake, append one line there.
