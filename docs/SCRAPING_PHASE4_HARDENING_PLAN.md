# Scraping Phase 4: Hardening & Drift

## Mål
Fase 4 gør scraping stabil i drift ved at:
- beskytte pipeline med guardrails
- gøre performance/kvalitet målbar med tydelige KPI'er
- etablere konkrete alerts til hurtig incident-response

---

## Implementeret i kode

### 1) Guardrails
- Provider toggles i backend config:
  - `scraping_provider_gnews_enabled`
  - `scraping_provider_serpapi_enabled`
  - `scraping_provider_configurable_enabled`
  - `scraping_provider_rss_enabled`
- Keyword budget pr. run:
  - `scraping_max_keywords_per_run`
- Configurable URL budgets:
  - `scraping_max_total_urls_per_run` (global extraction budget)
  - `DEFAULT_MAX_ARTICLES_PER_SOURCE` (per-source cap)
- Blind-domain circuit breaker:
  - `scraping_blind_domain_circuit_threshold`
  - Åbner circuit når et domæne gentagne gange giver 0-char extraction.

### 2) Observability
- Ny metric:
  - `scrape_guardrail_events_total{guardrail,provider,reason}`
- Eksisterende metrics bruges fortsat til runtime/succes/failures/dedup:
  - `scrape_run_duration_seconds`
  - `scrape_provider_duration_seconds`
  - `scrape_http_errors_total`
  - `scrape_extractions_total`
  - `scrape_playwright_fallback_total`
  - `scrape_duplicates_removed_total`

---

## Runtime-konfiguration (.env)

Eksempel:

```env
# Provider toggles
SCRAPING_PROVIDER_GNEWS_ENABLED=true
SCRAPING_PROVIDER_SERPAPI_ENABLED=true
SCRAPING_PROVIDER_CONFIGURABLE_ENABLED=true
SCRAPING_PROVIDER_RSS_ENABLED=true

# Budgets
SCRAPING_MAX_KEYWORDS_PER_RUN=50
SCRAPING_MAX_TOTAL_URLS_PER_RUN=200
SCRAPING_BLIND_DOMAIN_CIRCUIT_THRESHOLD=8

# Existing dedupe/rate controls
SCRAPING_FUZZY_DEDUP_ENABLED=true
SCRAPING_FUZZY_DEDUP_THRESHOLD=92
SCRAPING_FUZZY_DEDUP_DAY_WINDOW=2
SCRAPING_RATE_HTML_RPS=1.5
SCRAPING_RATE_API_RPS=3.0
SCRAPING_RATE_RSS_RPS=2.0
```

---

## Dashboard KPI'er (PromQL)

### p95 runtime (end-to-end)
```promql
histogram_quantile(
  0.95,
  sum(rate(scrape_run_duration_seconds_bucket[15m])) by (le)
)
```

### Timeout/fejlrate pr. provider
```promql
sum(rate(scrape_http_errors_total[10m])) by (provider, error_type)
```

### Extraction success-rate pr. domæne
```promql
sum(rate(scrape_extractions_total{result="success"}[15m])) by (domain)
/
clamp_min(sum(rate(scrape_extractions_total[15m])) by (domain), 0.001)
```

### JS/paywall pressure
```promql
sum(rate(scrape_extractions_total{result="empty_content"}[15m])) by (domain)
```

### Playwright fallback-rate
```promql
sum(rate(scrape_playwright_fallback_total{result="triggered"}[15m])) by (domain)
```

### Guardrail-hit rate
```promql
sum(rate(scrape_guardrail_events_total[15m])) by (guardrail, provider, reason)
```

---

## Alert-regler (forslag)

Konkrete regler er lagt i: `docs/PROMETHEUS_ALERTS_SCRAPING.yml`.

### Alert: Høj p95 runtime
- Trigger når p95 > 300s i 15 min.
- Severity: warning.

### Alert: Høj timeout-rate
- Trigger når `scrape_http_errors_total{error_type=~"connecttimeout|readtimeout|writetimeout"}` er over baseline i 10 min.
- Severity: warning/critical afhængigt af threshold.

### Alert: Lav extraction success-rate
- Trigger når success-rate pr. domæne < 20% i 30 min (og minimum volumen opfyldt).
- Severity: warning.

### Alert: Aggressiv guardrail-aktivering
- Trigger når `scrape_guardrail_events_total{guardrail="max_total_urls_per_run"}` stiger hurtigt.
- Trigger også ved mange `blind_domain_circuit` opens.
- Severity: warning.

---

## Drift-runbook (kort)

1. Tjek `scrape_guardrail_events_total`:
   - Hvis `max_keywords_per_run` eller `max_total_urls_per_run` stiger meget, justér budgets.
2. Tjek timeout-fejl pr. domæne:
   - Hvis isoleret domæne: sænk domæne-rate/cap, eller deaktiver kilde midlertidigt.
3. Tjek extraction success-rate:
   - Ved lav rate: opdater source config selectors eller aktiver Playwright fallback for domænet.
4. Tjek dedupe:
   - Hvis for aggressiv: sænk `SCRAPING_FUZZY_DEDUP_THRESHOLD`.
   - Hvis for mange near-dupes: hæv threshold eller udvid blocking-regler.

---

## Acceptance criteria for fase 4

- Guardrails udløses og måles via `scrape_guardrail_events_total`.
- Pipeline kan køre stabilt på tværs af flere brands uden runtime spikes fra enkelte domæner.
- Dashboards viser p95 runtime, fejlrate, extraction success-rate og fallback-rate tydeligt.
- Alert-regler giver signal før scraping-kvalitet eller hastighed kollapser.
