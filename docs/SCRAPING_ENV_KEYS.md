# Scraping Env Keys

Denne fil beskriver centrale miljøvariabler for scraping-throughput og guardrails.

## Throughput / Rate Limits

### `SCRAPING_RATE_HTML_RPS=1.5`
- Hvad styrer den: Maks antal HTML-sidekald pr. sekund pr. domæne (typisk `httpx` artikel/hjemmeside-kald).
- Hvorfor den findes: Beskytter mod blokeringer (`429`/timeouts) og reducerer belastning på mediesites.
- Hvis du hæver den: Hurtigere scraping, men større risiko for fejl og blokering.
- Hvis du sænker den: Mere stabilt og høfligt mod kilder, men langsommere run.

### `SCRAPING_RATE_API_RPS=3.0`
- Hvad styrer den: Maks antal API-kald pr. sekund (fx GNews/SerpAPI eller andre API-baserede kilder).
- Hvorfor den findes: Respekterer API-rate limits og reducerer fejl ved bursts.
- Hvis du hæver den: Kan give hurtigere svar, men kan ramme API-limit hurtigere.
- Hvis du sænker den: Mere robust mod rate-limit, men lavere throughput.

### `SCRAPING_RATE_RSS_RPS=2.0`
- Hvad styrer den: Maks antal RSS-relaterede HTTP-kald pr. sekund.
- Hvorfor den findes: Forhindrer unødige spikes mod feed-endpoints.
- Hvis du hæver den: Hurtigere feed-indlæsning, højere risiko for throttle på enkelte feeds.
- Hvis du sænker den: Mere stabil ingestion, langsommere feed-run.

## Scraping Guardrails

### `SCRAPING_MAX_KEYWORDS_PER_RUN=50`
- Hvad styrer den: Øvre grænse for antal keywords, der behandles i ét run.
- Hvorfor den findes: Forhindrer runaway-runs med meget høj CPU/netværksbelastning.
- Hvis du hæver den: Større dækningsgrad pr. run, men markant længere runtime.
- Hvis du sænker den: Hurtigere run og lavere load, men mindre dækningsgrad.

### `SCRAPING_MAX_TOTAL_URLS_PER_RUN=200`
- Hvad styrer den: Hård cap på hvor mange URL-kandidater der må hentes/behandles i ét run.
- Hvorfor den findes: Holder runtime og ressourceforbrug inden for et kontrolleret budget.
- Hvis du hæver den: Flere potentielle mentions, men større risiko for lange runs/timeouts.
- Hvis du sænker den: Hurtigere og billigere run, men risiko for at misse relevante artikler.

### `SCRAPING_BLIND_DOMAIN_CIRCUIT_THRESHOLD=8`
- Hvad styrer den: Antal gentagne “blinde” fejl for et domæne før circuit breaker åbner midlertidigt.
- Hvorfor den findes: Stopper spildkald mod kilder, der konsekvent fejler (fx paywall/anti-bot/parse-fail).
- Hvis du hæver den: Mere tålmodig mod ustabile domæner, men mere spildtid.
- Hvis du sænker den: Hurtigere fail-fast, men risiko for at skippe domæner der kun fejler kortvarigt.

## Anbefalet tuning-strategi

1. Start konservativt (nuværende defaults).
2. Mål run-varighed, fejlrate og mention-yield i Prometheus.
3. Justér én variabel ad gangen i små trin.
4. Lad ændringen køre i flere runs, før næste justering.
