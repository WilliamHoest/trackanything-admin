# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow Orchestration

### #1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
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
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### #5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### #6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
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
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

---

## Development Commands

```bash
# Activate virtualenv (always do this first)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run dev server (hot-reload)
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Syntax check before PR
python -m compileall app

# Operational scripts
python scripts/reset_scraping_test_state.py --dry-run   # preview reset
python scripts/reset_scraping_test_state.py --confirm   # apply reset
python scripts/run_scheduled_scrapes.py                 # trigger scheduled scrapes
```

**API docs when running:** `http://localhost:8000/docs` · `http://localhost:8000/health` · `http://localhost:8000/dev-info`

## Architecture

Clean Architecture with four strict layers — no cross-layer leakage:

```
app/
├── api/endpoints/          # HTTP only: routing, auth deps, HTTP status codes
├── services/               # Business logic, external APIs, orchestration
│   ├── scraping/           # Scraping subsystem (see below)
│   └── ai/                 # Atlas Intelligence (DeepSeek streaming)
├── crud/supabase_crud.py   # Single class for ALL Supabase table operations
├── schemas/                # Pydantic models: Create / Update / Response variants
└── core/                   # Config, Supabase client, logging, auth deps
```

**Adding a feature:** schemas → CRUD methods → service (if complex logic) → endpoint → register in `api/api_v1.py`.

**Endpoint naming convention:** files use `_supabase.py` suffix (e.g. `brands_supabase.py`).

## Scraping Subsystem

```
app/services/scraping/
├── orchestrator.py          # Aggregates all user keywords, runs all providers in parallel
├── pipeline.py              # Pipeline wrapper
├── providers/
│   ├── gnews.py             # GNews API
│   ├── serpapi.py           # SerpAPI (Google News)
│   ├── rss.py               # RSS feeds (DR, etc.)
│   └── configurable/        # Custom web scraping (Politiken, etc.)
├── core/
│   ├── date_utils.py        # All date parsing/normalization — use this, never roll your own
│   ├── text_processing.py   # URL normalization, keyword cleaning
│   ├── deduplication.py     # Near-duplicate detection across sources
│   └── metrics.py           # Prometheus metrics (exposed at /metrics)
└── analyzers/
    └── relevance_filter.py  # Optional AI relevance scoring
```

**Provider signature (all providers must match):**
```python
async def scrape_provider_name(
    keywords: List[str],
    from_date: datetime,
    to_date: datetime,
    scrape_run_id: Optional[str] = None
) -> List[Dict[str, Any]]:
```

Required output fields: `title`, `description`, `url`, `published_date`, `source`.

Providers are toggled per environment:
- `SCRAPING_PROVIDER_GNEWS_ENABLED=true/false`
- `SCRAPING_PROVIDER_SERPAPI_ENABLED=true/false`
- `SCRAPING_PROVIDER_CONFIGURABLE_ENABLED=true/false`
- `SCRAPING_PROVIDER_RSS_ENABLED=true/false`

## Authentication

`DEBUG=true` → mock user (no token required), ID `db186e82-e79c-45c8-bb4a-0261712e269c`.
`DEBUG=false` → Supabase JWT Bearer token validation.

Endpoints inject auth via:
```python
from app.core.config import settings
from app.security.auth import get_current_user
from app.security.dev_auth import get_dev_user
get_user = get_dev_user if settings.debug else get_current_user
```

## Critical Patterns

**Always validate ownership before mutations:**
```python
resource = await crud.get_resource(resource_id)
if not resource or resource.get("profile_id") != str(current_user.id):
    raise HTTPException(status_code=404, detail="Not found")
```

**All Supabase ops are synchronous calls on the client, wrapped in async functions:**
```python
async def get_brand(self, brand_id: int) -> Optional[Dict]:
    result = self.supabase.table("brands").select("*").eq("id", brand_id).execute()
    return result.data[0] if result.data else None
```

**Relationship loading via nested selects:**
```python
self.supabase.table("brands").select("*, topics(*, keywords(*))").execute()
```

## Environment Variables

```env
SUPABASE_URL=
SUPABASE_KEY=
DATABASE_URL=          # PostgreSQL URL (for direct SQL when needed)
DEEPSEEK_API_KEY=
GNEWS_API_KEY=
SERPAPI_KEY=
DEBUG=true
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

## Database / Migrations

Schema changes go in `migrations/` as SQL scripts, applied via Supabase SQL editor or psql. No ORM migrations — Supabase is the source of truth.

## Testing

No automated test suite exists yet. For manual validation: hit `/health`, exercise impacted endpoints, run `python -m compileall app`. Place future tests under `tests/` with names like `test_scraping_orchestrator.py`.

## Commit Style

Conventional Commits: `feat(scraping): ...`, `fix(chat): ...`, `refactor(ai): ...`. Keep commits scoped to one concern.
