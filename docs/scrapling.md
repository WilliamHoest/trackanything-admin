# Scrapling — Feature Documentation

Scrapling er det Python-bibliotek vi bruger til browser-baseret HTML-hentning i
`configurable`-provideren. Det tilbyder tre fetch-strategier, samt en AdaptiveSelector
til CSS-baseret indholdudtrækning der er robust over for DOM-ændringer.

Alle features er styret af feature flags og kan aktiveres uafhængigt af hinanden.

---

## Feature-oversigt

| Feature | Flag | Default | Hvad det giver |
|---|---|---|---|
| Scrapling Fetcher | `SCRAPING_USE_SCRAPLING` | `true` | Hurtig headless fetch med fingerprint-spoofing |
| StealthyFetcher | `SCRAPING_STEALTHY_FETCHER_ENABLED` | `false` | One-shot browser per URL, bedre WAF-bypass |
| AsyncStealthySession | `SCRAPING_STEALTHY_SESSION_ENABLED` | `false` | Persistent browser med tab-pool, hurtigste og mest robust |
| AdaptiveSelector | `SCRAPING_ADAPTIVE_SELECTOR_ENABLED` | `false` | Strukturbaseret CSS-matching der overlever DOM-ændringer |

---

## Extraction-kæde

Prioritetsrækkefølgen per artikel-URL (top vinder):

```
1. AsyncStealthySession   (hvis SCRAPING_STEALTHY_SESSION_ENABLED=true)
   ├── AdaptiveSelector   (hvis SCRAPING_ADAPTIVE_SELECTOR_ENABLED=true)
   └── BeautifulSoup      (config → generic → trafilatura)

2. StealthyFetcher / Scrapling Fetcher  (hvis SCRAPING_USE_SCRAPLING=true)
   ├── AdaptiveSelector   (hvis SCRAPING_ADAPTIVE_SELECTOR_ENABLED=true)
   └── BeautifulSoup      (config → generic → trafilatura)

3. Legacy httpx
   └── BeautifulSoup      (config → generic → trafilatura)

4. Playwright fallback    (last resort ved tomt indhold)
```

Et trin springes kun over hvis det returnerer tomt indhold — aldrig ved fejl alene.
Fejl logges og næste trin forsøges.

---

## Scrapling Fetcher

**Flag:** `SCRAPING_USE_SCRAPLING=true`

Den basale Scrapling-fetcher sender requests med realistiske browser-headere og
fingerprint-spoofing, uden at starte en rigtig browser. Hurtig og tilstrækkelig
for de fleste danske nyhedsmedier.

**Relevant kode:** `fetcher.py` → `_fetch_with_scrapling()`

---

## StealthyFetcher

**Flag:** `SCRAPING_STEALTHY_FETCHER_ENABLED=true`
(aktiverer automatisk `SCRAPING_USE_SCRAPLING`)

Starter en rigtig Chromium-browser per URL med avanceret fingerprint-spoofing
(skjuler `navigator.webdriver`, roterer fonts/screen sizes m.m.). Bedre mod
Cloudflare end den basale fetcher, men **langsom** — ny browser for hver URL.

Brug primært som mellemvej hvis `AsyncStealthySession` er for ressourcetung.

---

## AsyncStealthySession

**Flag:** `SCRAPING_STEALTHY_SESSION_ENABLED=true`

Genbruger én persistent Chromium-browser-kontekst med en **tab-pool** på tværs
af alle URL'er i et provider-run. Langt hurtigere end StealthyFetcher og mere
robust mod Cloudflare fordi browseren ser ud som en ægte browsersession.

### Konfiguration

| Env var | Default | Beskrivelse |
|---|---|---|
| `SCRAPING_STEALTHY_SESSION_ENABLED` | `false` | Aktivér/deaktivér session-mode |
| `SCRAPING_STEALTHY_SESSION_MAX_PAGES` | `3` | Antal parallelle tabs i browser-pool |
| `SCRAPING_STEALTHY_SESSION_TIMEOUT_MS` | `30000` | Request-timeout per URL (ms) |
| `SCRAPING_STEALTHY_SESSION_SOLVE_CLOUDFLARE` | `true` | Forsøg automatisk Cloudflare-challenge-løsning |
| `SCRAPING_STEALTHY_SESSION_DISABLE_RESOURCES` | `false` | Bloker billeder/fonts for hastighed |
| `SCRAPING_STEALTHY_SESSION_BLOCK_WEBRTC` | `true` | Bloker WebRTC for bedre fingerprint |
| `SCRAPING_STEALTHY_SESSION_RETRIES` | `1` | Antal retry-forsøg ved fetch-fejl |

### Lifecycle

Sessionen startes én gang i starten af `scrape_configurable_sources()` via
`contextlib.AsyncExitStack` og lukkes automatisk når provider-runnet er færdigt
— også ved exceptions. Ingen browser-process leaks.

```
provider-run start
  → AsyncStealthSessionManager.__aenter__()
    → AsyncStealthySession.start()
  → [alle URL-ekstrationer kører med session]
  → AsyncStealthSessionManager.__aexit__()
    → AsyncStealthySession.close()
provider-run slut
```

### Soft-fail semantik

Hvis sessionen ikke kan starte (scrapling ikke installeret, browser-fejl o.l.),
logges en advarsel og provider-runnet fortsætter med næste trin i extraction-kæden.
Sessionen crasher aldrig hele run.

### Relevant kode

- `stealth_session.py` — `AsyncStealthSessionManager` (context manager + fetch-wrapper)
- `manager.py` — session-initialisering og lifecycle via `AsyncExitStack`
- `fetcher.py` — `_fetch_with_stealthy_session()` + extraction-blok

### Metrics

| Label | Hvornår |
|---|---|
| `configurable_stealthy_session_success` | Session fetch + extraction gav indhold |
| `configurable_stealthy_session_failure` | Session fetch fejlede eller gav tomt indhold |

---

## AdaptiveSelector

**Flag:** `SCRAPING_ADAPTIVE_SELECTOR_ENABLED=true`

Scrapling's AdaptiveSelector gemmer CSS-selectorers **strukturelle egenskaber**
(tag, attributter, DOM-position, forældre) i en lokal SQLite-database, og kan
genfinde dem selv efter layout-ændringer via similaritetsmåling.

Eliminerer behovet for manuel selector-vedligeholdelse når danske nyhedsmedier
opdaterer deres DOM.

### Forudsætning

AdaptiveSelector kræver et Scrapling `Selector`-objekt (ikke BeautifulSoup).
Det oprettes direkte fra den HTML-streng vi allerede har fra Scrapling-fetch eller
StealthySession-fetch — ingen ekstra netværkskald.

AdaptiveSelector aktiveres kun når scraping sker via Scrapling eller StealthySession
(dvs. mindst ét af `SCRAPING_USE_SCRAPLING`, `SCRAPING_STEALTHY_FETCHER_ENABLED`,
`SCRAPING_STEALTHY_SESSION_ENABLED` skal være `true`).

### Extraction-niveauer

1. **Config-selectors** — domæne-specifikke CSS-selectors fra `source_configs` i Supabase,
   kørt med `adaptive=True, auto_save=True` → opbygger SQLite-træning
2. **Generiske selectors** — bred liste af standard artikel-selectors,
   kørt med `adaptive=True, auto_save=True` → opbygger SQLite-træning

Hvert vellykket match gemmes i SQLite så fremtidige requests kan genfinde indhold
selv efter DOM-ændringer.

### SQLite-storage

Placering: `adaptive_storage/adaptive_selectors.db` (i projektets rod, ignoreret af git)

```bash
# Verificer at data gemmes efter første scrape-run
sqlite3 adaptive_storage/adaptive_selectors.db "SELECT count(*) FROM storage;"
```

### Relevant kode

- `fetcher.py` — `_get_adaptive_storage_file()`, `_get_adaptive_storage()`,
  `_make_adaptive_selector()`
- `extractor.py` — `_extract_content_adaptive()`, `_extract_content_adaptive_sync()`

### Metrics

| Label | Hvornår |
|---|---|
| `configurable_adaptive_success` | Adaptive fandt indhold (config eller generic selectors) |
| `configurable_adaptive_failure` | Adaptive returnerede tomt — BeautifulSoup forsøges |

---

## Vejledning: Hvilken konfiguration skal jeg bruge?

**Minimal (default):**
```env
SCRAPING_USE_SCRAPLING=true
```
Fungerer godt for de fleste danske nyhedsmedier uden Cloudflare.

**Cloudflare-robusthed:**
```env
SCRAPING_USE_SCRAPLING=true
SCRAPING_STEALTHY_SESSION_ENABLED=true
SCRAPING_STEALTHY_SESSION_MAX_PAGES=3
```
Anbefales når sites blokerer basis-scrapling.

**Fuld pakke (max robusthed):**
```env
SCRAPING_USE_SCRAPLING=true
SCRAPING_STEALTHY_SESSION_ENABLED=true
SCRAPING_STEALTHY_SESSION_MAX_PAGES=3
SCRAPING_ADAPTIVE_SELECTOR_ENABLED=true
```
Giver bedst extract-rate og er DOM-ændring-resistent, men kræver mere ressourcer.

**Tuning-tip:** Start med `MAX_PAGES=3` og hold `PER_DOMAIN_EXTRACTION_CONCURRENCY`
uændret. Justér baseret på metrics efter 1-2 dages drift.

---

## Verifikation

```bash
# Syntakstjek
python -m compileall app/ -q

# Metrics (mens server kører)
curl localhost:8000/metrics | grep -E "stealthy_session|adaptive|scrapling"

# Verificer SQLite-træning (adaptive)
ls -la adaptive_storage/adaptive_selectors.db
sqlite3 adaptive_storage/adaptive_selectors.db "SELECT count(*) FROM storage;"
```
