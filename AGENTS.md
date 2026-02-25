# Repository Guidelines

## Project Structure & Module Organization
- `app/` contains the FastAPI backend.
- `app/api/endpoints/` holds HTTP route handlers; `app/api/api_v1.py` wires routers.
- `app/core/` contains config, logging, and shared infrastructure.
- `app/crud/` and `app/schemas/` define data access and payload models.
- `app/services/` contains domain logic, especially scraping (`app/services/scraping/`) and AI features (`app/services/ai/`).
- `scripts/` includes operational utilities (seed/reset/admin helpers).
- `migrations/` contains database migration assets; `docs/` stores design and reference docs.

## Build, Test, and Development Commands
- `python -m venv venv && source venv/bin/activate` creates/activates a local environment.
- `pip install -r requirements.txt` installs backend dependencies.
- `python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` runs the API locally.
- `python -m app.main` runs the app entrypoint directly.
- `python scripts/reset_scraping_test_state.py --dry-run` previews scrape-state reset actions.
- `python scripts/reset_scraping_test_state.py --confirm` applies reset actions.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and explicit type hints for new/changed code.
- Use `snake_case` for modules/functions/variables, `PascalCase` for classes, and clear verb-based function names.
- Keep endpoint handlers thin; place business logic in `app/services/`.
- Prefer shared utilities over duplicated logic (for scraping dates, use `app/services/scraping/core/date_utils.py`).
- No repository-wide formatter/linter config is currently enforced; keep style consistent with nearby files.

## Testing Guidelines
- There is currently no committed automated test suite or coverage gate in this repository.
- For changes, include reproducible manual validation steps in PRs (example: `/health`, impacted endpoints, scrape flow).
- For safety checks, run `python -m compileall app` before opening a PR.
- When adding tests, place them under a top-level `tests/` directory with descriptive names like `test_scraping_orchestrator.py`.

## Commit & Pull Request Guidelines
- Commit style in history favors Conventional Commit prefixes, e.g. `feat(scraping): ...`, `refactor(ai): ...`, `fix(chat): ...`.
- Keep commits focused and scoped to one concern.
- PRs should include: purpose, key files changed, validation evidence, and any config/env/migration impact.
- Link related issue(s) and add screenshots only when UI/dashboard behavior changes.

## Workflow Orchestration
### #1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don’t keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### #2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### #3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### #4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: “Would a staff engineer approve this?”
- Run tests, check logs, demonstrate correctness

### #5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask “is there a more elegant way?”
- If a fix feels hacky: “Knowing everything I know now, implement the elegant solution”
- Skip this for simple, obvious fixes — don’t over-engineer
- Challenge your own work before presenting it

### #6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don’t ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

---

## Task Management
1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check plan in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

---

## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what’s necessary. Avoid introducing bugs.
