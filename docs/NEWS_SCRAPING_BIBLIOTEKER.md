# Nyheds-scraping biblioteker i TrackAnything

## Formål
Dokumentet fokuserer på to ting:
- hvordan I udnytter biblioteker, I allerede bruger, bedre
- hvilke manglende biblioteker der giver størst næste gevinst

## Del 1: Maksimer biblioteker I allerede har

### `httpx` + `tenacity` + `fake-useragent`
- Nuværende brug:
  - `app/services/scraping/core/http_client.py`
  - retries på `429` + `5xx`, async client i providers
- Udnyt fuldt potentiale:
  - retry-guard: retry kun idempotente kald (`GET`, `HEAD`) medmindre en operation er dokumenteret idempotent
  - respekter `Retry-After` på `429`/`503` når header findes, før standard backoff
  - indfør per-domæne rate-limit (ikke kun global concurrency) for færre blokeringer
  - tilføj jitter i retry-wait for at undgå synkron retry-spikes
  - indfør "circuit breaker light" pr. domæne (fx 5 fejl i træk -> cooldown 5-15 min)
  - brug ens header-profiler per request-type (RSS/API/HTML) fremfor kun random UA
  - log retry-attempt metadata (domain, status, attempt) for bedre tuning
- Direkte gevinst:
  - højere success-rate pr. domæne
  - færre midlertidige bans
  - hurtigere fejlfinding på netværksfejl

### `beautifulsoup4` + `lxml` + `trafilatura`
- Nuværende brug:
  - `app/services/scraping/providers/configurable.py`
  - selector-baseret extraction med trafilatura fallback
- Udnyt fuldt potentiale:
  - kør trafilatura tidligere for domæner med kendt selector-ustabilitet
  - gem extraction-strategi pr. domæne i DB (fx `config`, `generic`, `trafilatura-first`)
  - indfør objektiv quality-gate (score 0-100) før fallback-strategi vælges
  - score kan baseres på tekstlængde, tekst/link-ratio, titel+dato tilstedeværelse og boilerplate-signaler
  - hvis score < threshold: eskalér deterministisk til næste strategi (ikke ad hoc)
  - mål extraction-kvalitet per strategi (tekstlængde, parse-success, keyword-hitrate)
  - normalisér boilerplate-blokke før keyword-match (navigation/footer/legal)
- Direkte gevinst:
  - højere andel brugbar artikeltekst
  - mindre støj i mentions
  - mindre manuelt vedligehold af selectors

### `dateparser`
- Nuværende brug:
  - dato parsing i `app/services/scraping/providers/configurable.py`
- Udnyt fuldt potentiale:
  - indfør confidence-felter ved dato-parse (high/medium/low)
  - gem rå dato-streng + parse-resultat til audit/tuning
  - undgå fallback til "nu" på svage datoer i alle providers (gælder især SerpAPI-flow)
  - ved lav confidence: gem `published_at = NULL` + `date_confidence=low` og håndtér særskilt i UI/rangering
  - brug kildeprioritet for dato: RSS `published/updated` > `schema.org datePublished` > side-tekst > ingen dato
- Direkte gevinst:
  - færre falske "nye" omtaler
  - mere præcis filtrering på `from_date`

### `feedparser`
- Nuværende brug:
  - `app/services/scraping/providers/rss.py`
- Udnyt fuldt potentiale:
  - brug feed `etag`/`modified` cache, så uændrede feeds giver billige checks
  - dedup på feed GUID + link + normalized title, ikke kun link
  - track `bozo_exception` statistik pr. feed for datakvalitet
- Direkte gevinst:
  - færre unødige feed-downloads
  - lavere duplikat-rate
  - bedre driftssignaler for problemfeeds

### `asyncio` orkestrering
- Nuværende brug:
  - parallel scraping i `app/services/scraping/orchestrator.py`
  - semafor i `app/services/scraping/providers/configurable.py`
- Udnyt fuldt potentiale:
  - split concurrency i to pools: discovery-pool og extraction-pool
  - indfør timeout budget per fase (discovery, fetch, extraction)
  - måling på queue-time og task-duration per provider
- Direkte gevinst:
  - mere stabil throughput under load
  - færre "slow source dræner hele run" situationer

## Del 2: Manglende biblioteker med størst ROI

### Prioritet 1: `rapidfuzz` (evt. suppleret med `simhash`)
- Problem:
  - nuværende dedupe i `fetch_all_mentions(...)` er URL-baseret
- Implementering:
  - ny fil: `app/services/scraping/core/deduplication.py`
  - 2-trins pipeline for performance: blocking (samme eTLD+1, samme dag +/-2 dage, titel-prefix hash) efterfulgt af fuzzy på kandidater (`rapidfuzz.fuzz.token_set_ratio(title)` + evt. simhash på brødtekst)
  - exact hash (`sha256`) beholdes til hurtig exact dedupe
  - threshold per kilde (fx højere threshold for RSS)
- Gevinst:
  - markant færre near-duplicates
  - højere kvalitet i digests/AI-svar
- Overvejelse imod:
  - kræver threshold tuning for at undgå false positives

### Prioritet 2: `aiolimiter`
- Problem:
  - I har concurrency-kontrol, men ikke egentlig request-rate kontrol per domæne
- Implementering:
  - limiter map pr. eTLD+1 (ikke kun hostname) i provider-laget
  - tilføj override-liste for særlige hosts (`m.`, `amp.`, CDN/subdomæner)
  - forskellige profiler: API-kilder vs. HTML-kilder
- Gevinst:
  - færre `429`
  - mere forudsigelig scraping latency
- Overvejelse imod:
  - ekstra konfigurations- og tuningbehov

### Prioritet 3: `prometheus-client`
- Problem:
  - logs er gode, men I mangler standardiserede runtime-metrics
- Implementering:
  - metrics endpoint i FastAPI
  - counters/histograms for requests, fejl, duplicates, extraction quality, latency
- Gevinst:
  - målbar forbedring af scrapingkvalitet
  - hurtigere root cause ved incidents
- Overvejelse imod:
  - kræver dashboard/alert opsætning for fuld værdi

### Prioritet 4: `sentry-sdk`
- Problem:
  - exceptions kan drukne i logs ved parallel scraping
- Implementering:
  - central exception capture med tags: provider, domain, scrape_run_id
- Gevinst:
  - hurtig prioritering af kritiske fejl
  - bedre historik over regressioner
- Overvejelse imod:
  - støj hvis event filtering ikke sættes ordentligt op

### Prioritet 5: `playwright` (kun fallback)
- Problem:
  - JS-renderede sider kan være tomme via normal HTTP-fetch
- Implementering:
  - brug kun fallback når extraction fejler eller content < minimum
  - enable per-domæne flag i source config
- Gevinst:
  - højere coverage på JS-tunge sites
- Overvejelse imod:
  - højere CPU/RAM + mere kompleks deployment

### Prioritet 6: `protego` (robots.txt parser)
- Problem:
  - mangler central governance af crawl-regler pr. domæne
- Implementering:
  - robots-check før discovery/extraction
  - cache robots-regler i memory med TTL
- Gevinst:
  - bedre compliance og lavere juridisk/operativ risiko
- Overvejelse imod:
  - kan reducere crawl-coverage på nogle domæner

### Prioritet 7: `tldextract`
- Problem:
  - domænegruppering er ofte forkert uden korrekt eTLD+1 parsing
- Implementering:
  - brug `tldextract` til limiter keys, metrics grouping og dedupe blocking
  - central helper i `app/services/scraping/core/domain_utils.py`
- Gevinst:
  - stabil per-domæne styring
  - færre kanttilfælde på `co.uk`-typer og subdomæner
- Overvejelse imod:
  - ekstra dependency, men lav integrationsrisiko

### Prioritet 8: `celery` + `redis` (først ved skaleringspres)
- Problem:
  - cron-script er simpelt, men begrænset ved høj kømængde/retry-behov
- Implementering:
  - flyt brand-scrapes til jobkø
  - behold API-endpoints som job-trigger/status
- Gevinst:
  - robust retries, bedre workload-fordeling, horizontal skalering
- Overvejelse imod:
  - markant højere systemkompleksitet

## Små high-ROI biblioteker (lav risiko)

### `orjson` (evt. `msgspec`)
- Brug:
  - hurtigere JSON serialisering/deserialisering i API-responser, logs og evt. jobpayloads
- Gevinst:
  - lavere CPU og latency ved store mention-lister
- Overvejelse imod:
  - kræver ensretning af JSON-håndtering i kritiske codepaths

### `pydantic-settings` + `python-dotenv` (allerede i projektet)
- Brug:
  - styr scraper-profiler via config: retry policies, limiter-profiler, dedupe-thresholds, quality-gates
- Gevinst:
  - hurtigere tuning uden code deploy
- Overvejelse imod:
  - kræver stram governance af env/config varianter

## Biblioteker I bør undgå lige nu
- `newspaper3k`: overlap med `trafilatura` og lav vedligeholdelsesværdi
- `aiohttp`: overlap med eksisterende `httpx` setup
- `selenium`: dårligere fit end `playwright` til moderne fallback-scenarier
- `scrapy`: kræver redesign af eksisterende provider-arkitektur
- nuance om `scrapy`: kan blive relevant som separat discovery-service senere, men ikke som direkte erstatning nu

## 30-dages konkret plan
1. Implementer `rapidfuzz` dedupe-lag og mål duplicate-rate før/efter.
2. Implementer `tldextract` + `aiolimiter` (eTLD+1 keys) og mål `429`-rate.
3. Tilføj quality-gate score i extraction-flow og mål parse-success per strategi.
4. Tilføj `prometheus-client` metrics for success/fail/latency/duplicates.
5. Tilføj `sentry-sdk` med tags for hurtig incident triage.

## Beslutningsregel for nye biblioteker
Et nyt bibliotek indføres kun, hvis mindst 2 af 4 er opfyldt:
- reducerer dokumenteret fejlrate eller datatab
- giver målbar performance- eller kvalitetsgevinst
- kan integreres uden stor arkitekturændring
- har en klar driftsejer (monitorering, opdatering, incident-håndtering)
