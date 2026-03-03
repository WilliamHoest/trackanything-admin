# Scraping Worker Architecture Plan

## Formaal
Flyt scraping vaek fra API-request lifecycle og over i dedikerede workers, saa scraping bliver:
- Hurtigere under load
- Mere stabil ved spikes
- Let at skalere horisontalt
- Uafhaengig af API pod scaling

Maalet er:
1. Flyt scraping til dedikerede workers (Celery/Arq/RQ + Redis).
2. Lad API kun enqueue jobs + laese status/resultat.
3. Horizontal scale workers uafhaengigt af API pods.
4. Behold nuvaerende limiter/circuit-breakers i worker-laget.

## Nuværende udgangspunkt
- Scraping koeres i API-processen via `process_brand_scrape(...)`.
- Providers koerer allerede parallelt med asyncio og guardrails.
- Rate limiter, domain circuit-breakers og dedup er implementeret i scraping services.

Det er en god base. Vi flytter orchestration-triggeren, ikke hele scraping-logikken.

## Teknologivalg (anbefaling)
Anbefalet: **Arq + Redis**
- Fordel: passer naturligt til async FastAPI/async scraping kode.
- Mindre boilerplate end Celery.
- God nok til ko/job/status/retry i denne arkitektur.

Alternativer:
- **Celery + Redis**: mest moden/feature-rig, men tungere opsaetning.
- **RQ + Redis**: simpelt, men mindre async-first.

## Target architecture
### API service (FastAPI)
- Validerer auth + ownership.
- Opretter job-record i DB.
- Enqueuer job i Redis queue.
- Returnerer `job_id` med det samme.
- Eksponerer job status/resultat endpoints.

### Worker service
- Lytter paa queue.
- Koerer eksisterende scraping flow (`process_brand_scrape`).
- Opdaterer job status (`running/succeeded/failed`).
- Skriver resultatsummary + fejl i job-record.

### Data storage
- Ny tabel: `scrape_jobs`.
- Valgfrit: `scrape_job_events` til detaljeret audit trail.

### Redis
- Queue backend + retry scheduling.
- Ikke source-of-truth for resultat (resultat ligger i DB).

## Foreslaaet data model
### `scrape_jobs`
- `id uuid pk`
- `profile_id uuid not null`
- `scope text not null` (`brand` | `user`)
- `brand_id int null`
- `status text not null` (`queued` | `running` | `succeeded` | `failed` | `cancelled`)
- `input_payload jsonb not null`
- `result_payload jsonb null`
- `error_text text null`
- `attempt int not null default 0`
- `max_attempts int not null default 3`
- `run_id text null`
- `worker_id text null`
- `queued_at timestamptz not null`
- `started_at timestamptz null`
- `finished_at timestamptz null`
- `heartbeat_at timestamptz null`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Indexes:
- `(profile_id, created_at desc)`
- `(status, queued_at)`
- `(brand_id, created_at desc)` where `brand_id is not null`

## API contract (foerste version)
### POST `/scraping/jobs/brand/{brand_id}`
Response:
- `job_id`
- `status` (`queued`)
- `queued_at`

### POST `/scraping/jobs/user`
Response:
- `job_id`
- `status` (`queued`)
- `queued_at`

### GET `/scraping/jobs/{job_id}`
Response:
- Job metadata
- Status
- Result summary (`mentions_found`, `mentions_saved`, `errors`)

### GET `/scraping/jobs`
Query:
- `status`
- `limit`
- `cursor` (eller offset)

Kun jobs for current user vises.

## Worker flow
1. Worker modtager `job_id`.
2. Marker job `running`, saet `started_at`, `worker_id`, `run_id`.
3. Koer eksisterende flow:
   - `process_brand_scrape(...)` for brand scope.
   - For user scope: iterer aktive brands (samme logik som i dag).
4. Gem `result_payload` + status.
5. Ved exception:
   - Opdater `attempt`.
   - Retry hvis `attempt < max_attempts`.
   - Ellers `failed`.

## Limiter/circuit-breakers (beholdes)
Ingen redesign af scraping-core er noedvendig.
- Behold `get_domain_limiter(...)` i worker-processen.
- Behold configurable domain circuit-breakers/blind-circuit logic.
- Behold nuvaerende guardrails (`max_keywords_per_run`, `max_total_urls_per_run` osv.).

Vigtigt:
- Disse controls skal leve i worker runtime, ikke i API laget.

## Implementeringsplan (faser)
### Fase 1 - Queue foundation
- Tilfoej Redis config i backend settings.
- Tilfoej queue adapter (`enqueue`, `dequeue`, `retry`).
- Tilfoej `scrape_jobs` migration + CRUD.

### Fase 2 - Worker service
- Opret worker entrypoint (`app/workers/scrape_worker.py`).
- Bind worker task til `job_id`.
- Implementer status transitions + retries.

### Fase 3 - API endpoints
- Nye `/scraping/jobs/*` endpoints.
- Flyt eksisterende `/scraping/brand/{id}` og `/scraping/user` til enqueue-flow
  (evt. behold sync endpoints bag feature flag i en overgang).

### Fase 4 - Scheduler integration
- Cron/scheduler enqueuer jobs i stedet for at scrape direkte.
- Tilfoej idempotency-key eller "one active job per brand" guard.

### Fase 5 - Drift og scale
- Koer worker deployment separat fra API deployment.
- Horizontal scale workers via replica count.
- Tune worker concurrency efter CPU/RAM/provider limits.

## Miljoevariabler (forslag)
- `SCRAPING_QUEUE_PROVIDER=arq`
- `REDIS_URL=redis://...`
- `SCRAPING_JOB_MAX_ATTEMPTS=3`
- `SCRAPING_JOB_TIMEOUT_S=900`
- `SCRAPING_WORKER_CONCURRENCY=8`
- `SCRAPING_WORKER_HEARTBEAT_S=15`

## Observability og drift
Tilfoej metrics:
- Queue depth
- Job wait time (`started_at - queued_at`)
- Job runtime (`finished_at - started_at`)
- Success/failure rate per scope
- Retry count

Logging:
- Log altid `job_id` + `run_id`.
- Link job status til eksisterende scrape run artifacts.

## Rollout strategi
1. Deploy queue + worker + job tabel.
2. Bag feature flag: enqueue kun for interne test users.
3. Sammenlign output mod nuvaerende sync flow (antal fund/saved/errors).
4. Skift default til async jobs.
5. Fjern eller begrans gamle sync endpoints.

## Acceptance criteria
- API svarer hurtigt (enqueue < 300 ms ved normal load).
- Ingen scraping execution i API requests.
- Worker kan restartes uden tab af jobs.
- Jobs er sporbare end-to-end via `job_id`.
- Samme eller bedre mention-kvalitet end nuvaerende flow.
