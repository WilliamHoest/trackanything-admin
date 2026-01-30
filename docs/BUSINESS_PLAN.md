# Business plan – TrackAnything (arbejdstitel)

## 1. Executive summary
TrackAnything er en web‑baseret medieovervågningsplatform, der i dag allerede kan oprette brand‑scopes med topics og keywords, scrape nyheder fra flere kilder, gemme mentions i Supabase, vise dem i et dashboard og analysere dem via en AI‑assistent med rapportarkiv. (Backend: `trackanything-admin/app/api/api_v1.py`, `trackanything-admin/app/services/scraping/orchestrator.py`, `trackanything-admin/app/services/ai/agent.py`; Frontend: `trackanything-app/src/app/[locale]/dashboard/*`, `trackanything-app/src/components/*`)

V1 bør fokusere på stabil, skalerbar web‑news monitoring (GNews, SerpAPI, RSS + konfigurerbare kilder), stærk brugeroplevelse for opsætning og overblik, samt Atlas‑rapporter som differentierende feature. Print/TV/radio og avanceret analytics skæres fra V1. (Kilder: `trackanything-admin/app/services/scraping/providers/*.py`, `trackanything-app/src/components/chat/atlas-intelligence.tsx`, `trackanything-app/src/components/reports/*`)

Differentieringen mod Infomedia er pris, enkelhed og “self‑service setup” – ikke fuld mediedækning i V1. Fokus er SMV/startups/bureauer i DK/Norden med korte time‑to‑value. (Antagelse)

Prisstrategi: 3‑4 tiers i DKK med klare limitere (brands/topics/keywords, mentions/måned, kilder, historik, seats, alerts) og add‑ons. “Minimum viable pricing” bør være attraktiv og simpel (B2B‑fakturering, 25% moms). (Se §9)

Omkostningsmodellen domineres af scraping‑APIer og AI‑inference (DeepSeek/Tavily). Der er allerede cost‑kontroller i koden (dedupe, batch‑insert, keyword‑filter, relevance‑filter), men V1 kræver planlagt scraping og hard caps per tier. (Kilder: `trackanything-admin/app/services/scraping/orchestrator.py`, `trackanything-admin/app/services/scraping/analyzers/relevance_filter.py`, `trackanything-admin/app/api/endpoints/scraping_supabase.py`, `trackanything-admin/app/crud/supabase_crud.py`)

---

## 2. Produktet i dag (hvad koden viser)

### 2.1 Arkitektur og stack
- **Frontend**: Next.js App Router med locales, Supabase Auth i browser og Orval‑genererede API hooks. (`trackanything-app/src/app/[locale]/*`, `trackanything-app/src/lib/supabase/client.ts`, `trackanything-app/src/lib/api/generated/*`)
- **Backend**: FastAPI + Supabase REST (CRUD via Supabase SDK), Pydantic schemas. (`trackanything-admin/app/main.py`, `trackanything-admin/app/crud/supabase_crud.py`, `trackanything-admin/app/schemas/*`)
- **AI**: PydanticAI agent med DeepSeek‑model; tools til web search og content fetch via Tavily, mention analysis og report‑workflow. (`trackanything-admin/app/services/ai/agent.py`, `trackanything-admin/app/services/ai/tools/*`, `trackanything-admin/app/services/ai/personas.py`)
- **Database**: Supabase tables for brands, topics, keywords, mentions, mention_keywords, generated_reports, chats/messages og source_configs. (`trackanything-admin/migrations/*.sql`)

### 2.2 Core funktioner (implementeret)
- **Brand‑/topic‑/keyword‑setup**
  - Backend CRUD endpoints for brands, topics og keywords. (`trackanything-admin/app/api/endpoints/brands_supabase.py`, `topics_supabase.py`, `keywords_supabase.py`)
  - Frontend flow til at oprette brand → topics → keywords (sheet‑wizard). (`trackanything-app/src/components/brands/create-brand-sheet.tsx`)
  - Overbliksliste med brand‑status, topics og keywords; toggles til at aktivere/deaktivere brands/topics. (`trackanything-app/src/components/brands/brands-topics-list.tsx`)

- **Scraping‑pipeline (web)**
  - Orchestrator kører GNews, SerpAPI, konfigurerbare kilder og RSS i parallel, deduper på normaliserede URLs. (`trackanything-admin/app/services/scraping/orchestrator.py`, `trackanything-admin/app/services/scraping/core/text_processing.py`)
  - Scraping‑endpoint bygger queries pr topic/keyword og kan bruge `query_template`. (`trackanything-admin/app/api/endpoints/scraping_supabase.py`, `trackanything-admin/migrations/008_add_query_template_and_mention_keywords.sql`)
  - AI relevance‑filtering via DeepSeek (fail‑open). (`trackanything-admin/app/services/scraping/analyzers/relevance_filter.py`)
  - Batch insert og dedupe i DB. (`trackanything-admin/app/crud/supabase_crud.py`)

- **Mentions feed + filtrering**
  - Mentions list med filtrering på brand/topic/keyword/platform, status og tidsvinduer; mark as read. (`trackanything-app/src/components/mentions/mentions-feed.tsx`, `trackanything-admin/app/api/endpoints/mentions_supabase.py`)

- **Analytics + Overview**
  - Frontend beregner KPIer (mentions, topics, platforme, tidsserie) fra mentions. (`trackanything-app/src/components/analytics/analytics-dashboard.tsx`, `trackanything-app/src/components/dashboard/overview-tab.tsx`)

- **Atlas AI chat + chat‑historik**
  - Streaming chat‑endpoint med Supabase‑profildata, mentions‑kontekst og persisterede chats/messages. (`trackanything-admin/app/api/endpoints/chat_supabase.py`, `trackanything-admin/migrations/002_create_chat_history.sql`)
  - Chat UI med prompt‑skabeloner og chat‑historik. (`trackanything-app/src/components/chat/atlas-chat.tsx`, `trackanything-app/src/hooks/use-chat.ts`)

- **Atlas AI rapporter**
  - Report CRUD i backend (generated_reports). (`trackanything-admin/app/api/endpoints/reports_supabase.py`, `trackanything-admin/migrations/005_create_generated_reports.sql`)
  - Report archive + viewer UI i frontend. (`trackanything-app/src/components/reports/report-archive.tsx`, `trackanything-app/src/components/reports/report-viewer.tsx`, `trackanything-app/src/components/chat/atlas-intelligence.tsx`)
  - AI tools til at hente mentions og gemme rapporter. (`trackanything-admin/app/services/ai/tools/reporting.py`)

- **Admin: bruger‑ og kildeadministration**
  - Admin‑API til brugere (opret/ret/slet) og admin‑UI. (`trackanything-admin/app/api/endpoints/admin_supabase.py`, `trackanything-app/src/app/[locale]/dashboard/admin/users/page.tsx`)
  - Admin‑API til source configs + AI‑analyse af URL (selectors + search pattern). (`trackanything-admin/app/api/endpoints/admin_sources.py`, `trackanything-admin/app/services/source_configuration/service.py`, `trackanything-app/src/app/[locale]/dashboard/admin/sources/page.tsx`)

### 2.3 Det, der fremgår i dokumenter men ikke er fuldt implementeret
- **Politiken/DR specifikke scrapers** er nævnt i docs, men der findes ikke provider‑kode specifikt til Politiken/DR; i stedet bruges configurable sources + RSS. [DOCS-ONLY] (`trackanything-admin/README.md`, `trackanything-admin/app/services/scraping/providers/configurable.py`, `trackanything-admin/app/services/scraping/providers/rss.py`)
- **Automatisk, planlagt scraping** er beskrevet i SCRAPING_LOGIC docs, men der er ingen scheduler i backend. [DOCS-ONLY] (`trackanything-admin/SCRAPING_LOGIC.md`, `trackanything-app/SCRAPING_LOGIC.md`)

---

## 3. Hvem er kunden? (ICP + personaer)

### ICP (første 12–18 mdr.)
- **SMV’er i DK/Norden** med PR/marketing/brand ansvar, der har behov for “good‑enough” web‑monitorering uden enterprise‑pris. (Antagelse)
- **Startups/SaaS** der vil tracke omtale, konkurrenter og trends uden komplekse enterprise‑kontrakter. (Antagelse)
- **Små bureauer** (PR/marketing) med behov for at monitorere flere kunder med simple dashboards og rapporter. (Antagelse)

### Personaer
1. **PR/kommunikationsansvarlig i SMV** – vil have dagligt overblik, simple alerts, og et hurtigt rapport‑format. (Antagelse)
2. **Founder/CMO i startup** – vil se trends/mentions uden opsætningstungt system, samt AI‑opsummeringer. (Antagelse)
3. **Bureaukonsulent** – vil kunne opsætte flere kundebrands hurtigt og dele rapporter. (Antagelse)

---

## 4. Problemet vi løser (jobs‑to‑be‑done)

- **“Jeg vil vide, hvornår vi bliver omtalt”** – centraliseret mentions‑feed med filtrering og status. (`trackanything-app/src/components/mentions/mentions-feed.tsx`)
- **“Jeg vil forstå hvad der betyder noget”** – Atlas chat + rapporter baseret på egne mentions. (`trackanything-admin/app/services/ai/agent.py`, `trackanything-app/src/components/chat/atlas-intelligence.tsx`)
- **“Jeg vil hurtigt opsætte overvågning”** – brand/topic/keyword wizard. (`trackanything-app/src/components/brands/create-brand-sheet.tsx`)
- **“Jeg vil kunne arbejde med flere scopes”** – brand‑scoped struktur og aktivering/deaktivering. (`trackanything-admin/migrations/006_add_brands_is_active.sql`, `trackanything-admin/app/schemas/brand.py`)

---

## 5. Konkurrentlandskab (Infomedia som baseline)

**Note:** Konkurrentmapping er baseret på generel markedserfaring, ikke på repo‑evidens. [ANTAGELSE]

### Must‑have parity items (min. V1)
- Web/news monitoring med pålidelig dedupe og historik.
- Filtrering på brand/topic/keyword/platform og eksportable rapporter.
- Notifikationer/alerts (minimum via webhook/email). [MANGLER]

### Differentieringspunkter vi kan vinde på
- **Pris og enkelhed**: hurtig opsætning og lavere total cost.
- **AI‑drevne rapporter og chat** direkte fra kundens mentions (implementeret). (`trackanything-admin/app/services/ai/tools/reporting.py`, `trackanything-app/src/components/reports/*`)
- **Self‑service kildeopsætning** via AI‑baseret selector‑analyse. (`trackanything-admin/app/services/source_configuration/*`, `trackanything-app/src/app/[locale]/dashboard/admin/sources/page.tsx`)

### Ting vi bør undgå tidligt
- Fuldt print/TV/radio‑paritet.
- Tunge enterprise‑workflows (kompleks approvals, SSO/SAML, on‑prem). [MANGLER]
- Store dashboards med BI‑niveau KPI’er før vi har stabil data‑kvalitet.

---

## 6. Positionering og differentiering

**Positionering:** “Den billige, brugervenlige, AI‑assisterede media‑monitoring platform for SMV’er i Norden.”

**Kerne‑budskab:**
- Sæt det op på 10 minutter (brand → topics → keywords). (`trackanything-app/src/components/brands/create-brand-sheet.tsx`)
- Få dagligt overblik med mentions, filtrering og AI‑opsummeringer. (`trackanything-app/src/components/mentions/mentions-feed.tsx`, `trackanything-app/src/components/chat/atlas-chat.tsx`)
- Byg egne kilder via admin‑kildeanalyse (AI selectors). (`trackanything-admin/app/services/source_configuration/service.py`)

---

## 7. V1 scope (Definition of Done)

### Funktionelt scope
1. **Stabil scraping + dataflow**
   - Automatiseret scraping pr brand baseret på `scrape_frequency_hours` og `last_scraped_at`. [MANGLER] (felter findes i DB). (`trackanything-admin/migrations/add_scrape_frequency.sql`, `trackanything-admin/migrations/006_add_brands_is_active.sql`)
   - Kilde‑mix: GNews + SerpAPI + RSS + konfigurerbare kilder med selector‑configs. (`trackanything-admin/app/services/scraping/providers/*.py`)

2. **Brand/topic/keyword CRUD fuldt i UI**
   - Opret, rediger, deaktiver, slet både topics og keywords (kun delvist i UI i dag). (`trackanything-app/src/components/brands/brands-topics-list.tsx`, `trackanything-admin/app/api/endpoints/topics_supabase.py`, `keywords_supabase.py`)
   - UI for `query_template`. [MANGLER] (`trackanything-admin/app/schemas/topic.py`, `trackanything-admin/app/api/endpoints/scraping_supabase.py`)

3. **Mentions workflow**
   - Filtrering, read/unread, keyword‑matches og batch‑performance. (`trackanything-app/src/components/mentions/mentions-feed.tsx`, `trackanything-admin/app/crud/supabase_crud.py`)

4. **Atlas Chat + Reports**
   - Stabil streaming chat, chat‑historik, rapportarkiv. (`trackanything-admin/app/api/endpoints/chat_supabase.py`, `trackanything-admin/app/api/endpoints/reports_supabase.py`, `trackanything-app/src/components/chat/atlas-intelligence.tsx`)

5. **Baseline admin**
   - Admin user‑styring og kilde‑opsætning (AI‑analyse). (`trackanything-admin/app/api/endpoints/admin_supabase.py`, `admin_sources.py`, `trackanything-app/src/app/[locale]/dashboard/admin/*`)

### Non‑functional requirements (DoD)
- **Sikkerhed**: Supabase RLS aktiveret på centrale tabeller; admin‑rolle check. (`trackanything-admin/migrations/*.sql`, `trackanything-admin/app/security/auth.py`)
- **Stabilitet/Uptime**: Backend opsættes som container (Dockerfile) og frontend på Vercel. (`trackanything-admin/Dockerfile`, `trackanything-app/vercel.json`)
- **Logging/observability**: Standard logging i backend, især scraping/AI. (`trackanything-admin/app/main.py`, `trackanything-admin/app/api/endpoints/scraping_supabase.py`)
- **GDPR‑readiness**: Dataminimering, sletteflow for reports/mentions, databehandleraftaler og EU‑hosting. [ANTAGELSE] (mangler eksplicit i kode).
- **Billing readiness**: Simple plan‑limiters og usage‑målinger; ingen integration i kode endnu. [MANGLER]

### V1 DoD – målbare kriterier
1. **Scheduler kører autonomt**: Scraping kører uden manuel trigger og scraper aktive brands efter `scrape_frequency_hours` med jitter (±10 min) for load‑spredning. [MANGLER]
2. **95% scraping‑succes**: Mindst 95% af scraping‑jobs fuldføres uden exception; failures logges med job‑id og brand‑id. (`trackanything-admin/app/services/scraping/orchestrator.py`)
3. **Mentions‑performance**: Mentions feed kan pagineres (≥50 pr side) og loader under 2 sek ved 10.000 mentions i DB. (`trackanything-admin/app/api/endpoints/mentions_supabase.py`)
4. **Plan limits server‑side**: Brands/topics/keywords‑caps og scrapes/dag og mentions‑cap håndhæves server‑side (ikke kun UI). [MANGLER]
5. **GDPR‑minimum**: "Slet konto + eksportér data" fungerer for brugere. [MANGLER]

### QA checklist
- Mentions kan filtreres på brand/topic/keyword/platform, og read/unread persisterer. (`trackanything-admin/app/api/endpoints/mentions_supabase.py`)
- Atlas kan generere og gemme rapporter via chat. (`trackanything-admin/app/services/ai/tools/reporting.py`)
- Admin kan tilføje og refresh source configs, og kilder bruges i scraping. (`trackanything-admin/app/services/source_configuration/service.py`, `trackanything-admin/app/services/scraping/providers/configurable.py`)
- Batch inserts, dedupe og pagination fungerer korrekt. (`trackanything-admin/app/crud/supabase_crud.py`)

---

## 8. Produkt-roadmap (V1 → V1.5 → V2)

### V1 (0–4 mdr.) – “Stabil kerne + AI‑rapporter”
- Implementér scheduler til scraping pr brand (baggrundsjob/cron). [MANGLER]
- Fuld CRUD i UI for topics/keywords + query_template UI.
- Forbedret alert/digest (mindst webhook) med UI for integration_configs. [DELVIST] (backend service findes). (`trackanything-admin/app/services/digest_service_supabase.py`)

### V1.5 (4–8 mdr.) – “Kvalitet & vækst”
- Forbedrede analytics (trends, sentiment). [MANGLER]
- Brugerstyring (invites/seats) og team‑arbejde.
- Kildelibrary + templates (standardiserede danske medier via source_configs).

### V2 (8–18 mdr.) – “Enterprise light”
- Avancerede alerts, SLA, længere historik, API‑adgang.
- (Hvis strategisk) udvidelse til print/TV/radio via partnerskaber. [ANTAGELSE]

---

## 9. Pris- og pakke-strategi (DKK, tiers, add-ons)

**Antagelser:** Fokus på SMV/startups/bureauer. Ikke public sector først. Web/news/RSS i V1, ingen fuld print/TV/radio‑paritet. [ANTAGELSE]

### Value metric og cost drivers
- **Value metric (primær):** Mentions pr. måned + antal brands. Seats er sekundær limiter.
- **Cost drivers (primær):** Provider‑searches (GNews, SerpAPI) + sekundært storage/egress. AI‑inference (DeepSeek) er næsten neglicerbart (se §9A).
- **Vigtigste plan‑limiter:** Mentions cap – det er det element der styrer både kundeværdi og variable cost. Når cap nås, stoppes scraping for den pågældende brand/plan.

### Tiers (eksempel, ekskl. moms)
1. **Starter – 299 DKK/md**
   - 1 brand, 5 topics, 25 keywords
   - 1.000 mentions/md
   - Kilder: RSS + GNews
   - Historik: 30 dage
   - 1 seat

2. **Pro – 799 DKK/md**
   - 3 brands, 20 topics, 150 keywords
   - 10.000 mentions/md
   - Kilder: RSS + GNews + SerpAPI
   - Historik: 12 mdr
   - 3 seats
   - 1 ugentlig AI‑rapport (via Atlas)

3. **Business – 2.499 DKK/md**
   - 10 brands, 50 topics, 500 keywords
   - 50.000 mentions/md
   - Kilder: alle (inkl. configurable sources)
   - Historik: 24 mdr
   - 10 seats
   - 4 rapporter/md + “kritisk alert”

4. **Enterprise – fra 6.999 DKK/md**
   - Custom limits, SLA, SSO, API adgang, onboarding.

### Add‑ons
- Ekstra seats (fx 99 DKK/md pr seat)
- Ekstra historik (fx +12 mdr)
- Ekstra kilder (enterprise media packs)
- API‑adgang (export/BI)
- “Agency mode” (multi‑kunde workspace)

### Minimum viable pricing (launch)
- **Starter 299 DKK** og **Pro 799 DKK** med tydelige limits og 25% moms pålagt i checkout.
- Tilbyd **B2B faktura** (CVR) og månedlig/årlig betaling.
- Gør plan‑limits synlige direkte i UI (mentions‑forbrug og brand‑caps).

---

## 9A. Omkostningsmodel (hosting + AI + scraping providers)

### A) Hosting baseline (today / V1)
**Backend hosting (Railway)**
- Railway Hobby‑planen fungerer som pay‑as‑you‑go med **$5 inkluderet ressourceforbrug pr. måned**. Bruger man under $5, betaler man reelt $0; ellers betales differencen. Backend runtime er defineret i `trackanything-admin/Dockerfile` (Python 3.11‑slim + Uvicorn). (`trackanything-admin/Dockerfile`)

**Frontend hosting (Vercel)**
- Repo har `vercel.json` med Next.js‑framework og sikkerhedsheaders, men planvalg er ikke angivet. (`trackanything-app/vercel.json`)
- **Vercel Hobby (gratis)** inkluderer bl.a. ~100 GB Fast Data Transfer/måned. **Vercel Pro** inkluderer ~1 TB/måned og prissættes per seat + usage ved overforbrug. Præcise limits bør verificeres på Vercels pricing‑side.

**Database/Auth (Supabase)**
- Supabase bruges til auth og alle data (brands/topics/mentions/reports/etc.). (`trackanything-admin/app/core/config.py`, `trackanything-admin/app/core/supabase_client.py`, `trackanything-admin/migrations/*.sql`)
- **Supabase Free** har inkluderede kvoter (bl.a. 500 MB database storage, 50K auth MAU). **Supabase Pro** starter ved $25/måned base og har større inkluderede kvoter (bl.a. 8 GB database storage) med overage‑betaling ved overforbrug. Præcise kvoter og overage‑priser bør verificeres på Supabase pricing‑side.
- **Cost drivers**: DB‑storage for mentions + reports, egress, og RLS overhead ved større volumen.

**Hosting‑scenarier (V1)**

| | Scenario A (billigst) | Scenario B (komfort) |
|---|---|---|
| **Backend** | Railway Hobby ($5 inkl.) | Railway Hobby ($5 inkl.) |
| **Frontend** | Vercel Hobby ($0) | Vercel Pro (~$20/seat) |
| **Database** | Supabase Pro ($25 base) | Supabase Pro ($25 base) |
| **Estimeret total** | **~$30 / ~204 DKK** | **~$50–75 / ~340–510 DKK** |

- **Scenario A** er tilstrækkeligt til launch og early traction (lav trafik, 1 developer seat).
- **Scenario B** giver komfort (mere bandwidth, team seats, preview deploys) og vælges når trafikken kræver det.

> **Bemærk:** Alle tre platforme har usage‑baserede komponenter. Faktisk cost afhænger af trafik, storage og antal seats. Planvalg og priser er ikke i repo og skal verificeres på leverandørernes pricing‑sider før lancering.

### B) Variable costs & unit economics
**AI‑providers i kode**
- **DeepSeek**: chat + relevance filter + source config analyse. (`trackanything-admin/app/services/ai/agent.py`, `trackanything-admin/app/services/scraping/analyzers/relevance_filter.py`, `trackanything-admin/app/services/source_configuration/analyzers/ai_analyzer.py`)
- **Tavily**: web search og content fetch. (`trackanything-admin/app/services/ai/tools/web_search.py`, `content_fetch.py`)

**Typiske AI‑calls pr workflow**
- **Chat turn**: 1 DeepSeek completion pr user message (streaming). (`trackanything-admin/app/api/endpoints/chat_supabase.py`)
- **Relevance filter**: 1 DeepSeek call pr scraped mention (parallel). (`trackanything-admin/app/services/scraping/analyzers/relevance_filter.py`)
- **Rapport**: 1+ DeepSeek calls til generering + tool call for data + save. (`trackanything-admin/app/services/ai/tools/reporting.py`)

**DeepSeek API officielle priser (deepseek‑chat / DeepSeek V3)**
Kilde: DeepSeek API pricing docs.

| Token‑type | Pris pr. 1M tokens |
|---|---|
| Input (cache hit) | $0,07 |
| Input (cache miss) | $0,27 |
| Output | $1,10 |

**Cost‑per‑1000 mentions (relevansfilter)**
Baseret på kode‑analyse af `relevance_filter.py`: ~300 input tokens + 5 output tokens pr. mention (600 chars tekst + prompt, `max_tokens=5`).

| Scenarie | Input tokens (1K mentions) | Output tokens (1K mentions) | Input cost | Output cost | **Total** |
|---|---|---|---|---|---|
| Cache miss | 300.000 | 5.000 | $0,081 | $0,0055 | **$0,087 (~0,6 DKK)** |
| Cache hit | 300.000 | 5.000 | $0,021 | $0,0055 | **$0,027 (~0,2 DKK)** |

**Cost‑per‑report**
Baseret på kode‑analyse af `reporting.py`: ~4.000 input tokens (500 mentions × ~3 tokens + prompt/context) + ~2.000 output tokens (rapport‑tekst).

| Scenarie | Input | Output | **Total** |
|---|---|---|---|
| Cache miss | $0,0011 | $0,0022 | **$0,003 (~0,02 DKK)** |

**Cost‑per‑chat‑besked**
Baseret på `ai/__init__.py` + `personas.py`: ~2.000 input tokens (system prompt + historie) + ~500 output tokens.

| Scenarie | Input | Output | **Total** |
|---|---|---|---|
| Cache miss | $0,00054 | $0,00055 | **$0,001 (~0,007 DKK)** |

> **Konklusion:** AI‑inference via DeepSeek V3 er ekstremt billigt. Selv ved 100.000 mentions/md er AI‑omkostningen under $9 (~61 DKK). De primære variable omkostninger er scraping‑provider fees (GNews, SerpAPI).

**Scraping/news providers (pris ikke i repo – antagelse)**
- **GNews API**: bruges hvis `GNEWS_API_KEY` er sat. (`trackanything-admin/app/services/scraping/providers/gnews.py`, `trackanything-admin/app/core/config.py`)
- **SerpAPI**: bruges hvis `SERPAPI_KEY` er sat. (`trackanything-admin/app/services/scraping/providers/serpapi.py`)
- **RSS (Google News)**: gratis men rate‑limited. (`trackanything-admin/app/services/scraping/providers/rss.py`)
- **Configurable sources**: bruger HTML scraping; primær cost er CPU/egress. (`trackanything-admin/app/services/scraping/providers/configurable.py`)

**Provider‑priser (TODO – skal verificeres på leverandørens pricing‑side)**
- **GNews**: Pris ikke i repo. Interval‑antagelse: $0–$20 pr. 1.000 queries afhængig af plan. Verificér på gnews.io/pricing.
- **SerpAPI**: Pris ikke i repo. Interval‑antagelse: $5–$50 pr. 1.000 queries afhængig af plan. Verificér på serpapi.com/pricing.
- **Tavily**: Pris ikke i repo. Bruges kun on‑demand i AI‑chat. Verificér på tavily.com/pricing.

> **Action item:** Indhent aktuelle priser og free‑tier limits fra alle tre leverandører inden launch‑budgettering.

**Enkelt model‑formel**
```
Variable cost pr måned ≈
  (mentions * cost_per_mention_ai)
+ (searches * cost_per_search_provider)
+ (reports * cost_per_report_ai)
```

### C) Cost controls
**Eksisterende cost‑controls i kode**
- Deduplication på normaliserede URLs før DB‑insert. (`trackanything-admin/app/services/scraping/orchestrator.py`)
- Batch‑inserts og upserts med chunking. (`trackanything-admin/app/crud/supabase_crud.py`)
- Keyword‑cleaning og matching for at reducere støj. (`trackanything-admin/app/services/scraping/core/text_processing.py`)
- AI relevance‑filter med korte prompts og fail‑open. (`trackanything-admin/app/services/scraping/analyzers/relevance_filter.py`)
- `is_active` og `scrape_frequency_hours` felter i brands. (`trackanything-admin/app/schemas/brand.py`, `trackanything-admin/migrations/add_scrape_frequency.sql`)

**Foreslåede cost‑controls (V1)**
1. **Plan‑baserede kildebegrænsninger** (Starter = RSS+GNews; Pro = +SerpAPI; Business = configurable).
2. **Scheduler der respekterer `scrape_frequency_hours`** (undgå for hyppige runs).
3. **Max keywords per topic og max queries pr brand pr dag**.
4. **Cachning af search‑resultater pr query i 24–48 timer**.
5. **Slå relevance‑filter fra på laveste tier eller kør “sampled” filtrering**.
6. **Rate‑limit på RSS og configurable sources**.
7. **Per‑tier “mentions cap”** med stop‑scrape når cap er nået.
8. **Batching af keywords** (allerede delvist via OR‑queries i GNews/SerpAPI). (`gnews.py`, `serpapi.py`)

### D) Break‑even table (simple)

**Nøglerelation: brand‑scrapes → mentions**
Provider‑priser afregnes pr. query/brand‑scrape, men value og AI‑cost afregnes pr. mention. Forholdet er:
- **1 brand‑scrape → ~5–30 mentions** (afhængig af niche og keyword‑specificitet). [ANTAGELSE]
- Konservativt estimat: **1 brand‑scrape → 10 mentions** bruges i beregningen nedenfor.

**Antagelser (med‑scenario)**
- 1 USD ≈ 6,8 DKK
- AI cost (DeepSeek, officielle priser): ~0,6 DKK pr. 1.000 mentions (relevansfilter) + ~0,02 DKK pr. rapport
- Scraping‑provider cost: [ANTAGELSE] ~5–15 DKK pr. 1.000 brand‑scrapes (GNews + SerpAPI; **skal verificeres**)
- Ved 10 mentions/scrape svarer ~5–15 DKK pr. 1.000 scrapes til ~0,5–1,5 DKK pr. 1.000 mentions (provider) + ~0,6 DKK pr. 1.000 mentions (AI)
- Samlet variable cost antagelse: **~2–3 DKK pr. 1.000 mentions** (AI + provider, ved 10 mentions/scrape)
- Rapport cost: **~0,05 DKK pr. rapport** (neglicerbar)
- Avg usage per customer: **5.000 mentions + 4 rapporter pr. måned**
- Avg price (ARPA): **799 DKK pr. måned**
- Fast hosting (V1, Scenario A): ~204 DKK/md

| Kunder | Mentions/md | Scrapes/md (÷10) | Omsætning (DKK) | Variable cost (DKK) | Fast cost (DKK) | Bruttomargin |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 50.000 | 5.000 | 7.990 | ~125 | 204 | **~96%** |
| 50 | 250.000 | 25.000 | 39.950 | ~625 | 340 | **~98%** |
| 200 | 1.000.000 | 100.000 | 159.800 | ~2.500 | 510 | **~98%** |

> **OBS 1:** Marginen er høj primært pga. lave DeepSeek‑priser og gratis kilder (RSS, configurable). Hvis mention‑density er lavere (fx 5 mentions/scrape i stedet for 10), fordobles provider‑cost‑andelen.
> **OBS 2:** Hvis GNews/SerpAPI priser ligger i den høje ende af intervallet, kan variable costs stige 2–3x. **Provider‑priser skal verificeres inden skalering.**
> **OBS 3:** Tabellen ekskluderer løn, marketing og andre driftsomkostninger. Den viser kun infrastruktur‑margin.

---

## 10. Go‑to‑market (kanaler, salg, onboarding)

### Første målsegmenter (DK/Norden)
- SMV’er i PR/marketing/kommunikation
- Startups med internationalt fokus
- Små bureauer med 2–10 kunder

### Kanaler
- **Self‑serve**: produkt‑ledet onboarding (gratis trial, kort setup‑wizard).
- **Partnerskaber**: bureauer og PR‑netværk.
- **Content marketing**: “monitoring templates” og use‑cases (kriser, konkurrenter, regulatorisk).

### Onboarding‑flow (V1)
- Login → Opret brand → topics/keywords → manual scrape → første rapport.
  (Understøttet af `create-brand-sheet` + `manual-scrape-dialog` + Atlas Reports.)
  (`trackanything-app/src/components/brands/create-brand-sheet.tsx`, `trackanything-app/src/components/scraping/manual-scrape-dialog.tsx`, `trackanything-app/src/components/chat/atlas-intelligence.tsx`)

---

## 11. Drift, compliance og risiko (GDPR, datasikkerhed, legal)

- **GDPR**: data består primært af offentlige mentions + brugernes egne profiler. Kræver databehandleraftaler, sletteflows og klart formål. [ANTAGELSE] (ikke udtrykt i kode).
- **Datasikkerhed**: Supabase RLS er aktivt på centrale tabeller (migrations). (`trackanything-admin/migrations/*.sql`)
- **Auth**: Supabase JWT i produktion; dev‑auth i debug. (`trackanything-admin/app/security/auth.py`)
- **Risiko**: Scraping‑kilder kan blokere eller ændre HTML; configurable sources reducerer risiko men kræver vedligehold. (`trackanything-admin/app/services/source_configuration/service.py`)

### Konkrete mitigations (V1‑krav)
1. **Kun metadata**: Gem kun titel, teaser, URL, tidspunkt og kilde – ingen fuldtekst‑kopiering. (Allerede implicit i kode: `content_teaser` er max 600 chars.) (`trackanything-admin/app/services/scraping/analyzers/relevance_filter.py:43`, `trackanything-admin/app/api/endpoints/scraping_supabase.py:234`)
2. **Respektér `robots.txt`** for configurable sources – eller dokumentér policy eksplicit. [MANGLER] (`trackanything-admin/app/services/scraping/providers/configurable.py`)
3. **Source kill‑switch**: Admin skal kunne disable en kilde globalt med ét klik (allerede delvist understøttet via `is_active` på source configs). [DELVIST] (`trackanything-admin/app/api/endpoints/admin_sources.py`)

---

## 12. KPI’er og succesmål

- **Activation**: % der opretter første brand+topic+keyword og kører første scrape (V1 mål >40%).
- **Retention (30/90‑dage)**: aktive brugere der åbner mentions/Atlas ugentligt.
- **Mentions kvalitet**: % af mentions markeret “read” og gennemsnitlig “relevance” (proxy via AI filter hit‑rate).
- **Rapport‑brug**: # rapporter pr bruger/måned.
- **Unit economics**: cost per 1.000 mentions vs ARPA (se §9A).

---

## 13. Appendix: Feature inventory + repo evidence

### Current Product Inventory

**Implementeret (frontend + backend)**
- Brand/topic/keyword CRUD via API og frontend setup‑wizard. (`trackanything-admin/app/api/endpoints/brands_supabase.py`, `topics_supabase.py`, `keywords_supabase.py`, `trackanything-app/src/components/brands/create-brand-sheet.tsx`)
- Scraping pipeline (GNews, SerpAPI, RSS, configurable sources) + dedupe + relevance filter. (`trackanything-admin/app/services/scraping/*`)
- Mentions feed med filtrering og read/unread. (`trackanything-app/src/components/mentions/mentions-feed.tsx`, `trackanything-admin/app/api/endpoints/mentions_supabase.py`)
- Analytics/overview baseret på mentions. (`trackanything-app/src/components/analytics/analytics-dashboard.tsx`, `trackanything-app/src/components/dashboard/overview-tab.tsx`)
- Atlas AI chat med chat‑historik + reports archive/viewer. (`trackanything-admin/app/api/endpoints/chat_supabase.py`, `trackanything-admin/app/api/endpoints/reports_supabase.py`, `trackanything-app/src/components/chat/atlas-intelligence.tsx`)
- Admin user management. (`trackanything-admin/app/api/endpoints/admin_supabase.py`, `trackanything-app/src/app/[locale]/dashboard/admin/users/page.tsx`)
- Admin source configuration + AI selector analysis. (`trackanything-admin/app/api/endpoints/admin_sources.py`, `trackanything-admin/app/services/source_configuration/service.py`, `trackanything-app/src/app/[locale]/dashboard/admin/sources/page.tsx`)

**[DELVIST] (backend findes, UI mangler eller flow ufuldstændigt)**
- `query_template` pr topic (backend + scraping, UI mangler). [DELVIST] (`trackanything-admin/app/schemas/topic.py`, `trackanything-admin/app/api/endpoints/scraping_supabase.py`)
- Digest/webhook integration (service + endpoint; ingen UI til config). [DELVIST] (`trackanything-admin/app/services/digest_service_supabase.py`, `trackanything-admin/app/api/endpoints/digests_supabase.py`)
- Profile/settings UI uden backend‑binding. [DELVIST] (`trackanything-app/src/app/[locale]/dashboard/settings/page.tsx`, `trackanything-app/src/app/[locale]/dashboard/profile/page.tsx`)

**[MANGLER] (vigtige for V1)**
- Scheduler/cron der respekterer `scrape_frequency_hours` og `last_scraped_at`. [MANGLER] (`trackanything-admin/migrations/add_scrape_frequency.sql`, `trackanything-admin/migrations/006_add_brands_is_active.sql`)
- UI for topic/keyword redigering, sletning og query_template. [MANGLER]
- Alerts/notifications (email/webhook) i UI og plan‑limits. [MANGLER]
- Plan‑/billing‑styring og usage tracking. [MANGLER]

### System boundaries (hvad TrackAnything IKKE er i V1)
- **Ikke social media monitoring** – ingen integration med Facebook, X/Twitter, Instagram, LinkedIn eller TikTok. Kun web/news/RSS.
- **Ikke paywall scraping** – systemet gemmer metadata og teasers fra offentligt tilgængelige kilder; ingen paywall‑omgåelse.
- **Ikke komplet arkiv** – historik er tier‑begrænset (30 dage → 24 mdr). Ikke en erstatning for Infomedia‑arkiv eller compliance‑arkivering.
- **Ikke enterprise procurement** – ingen SSO/SAML, on‑prem, SLA‑kontrakter eller dedicated infrastructure i V1.

### Repo evidence (udvalg)
- API router og endpoints: `trackanything-admin/app/api/api_v1.py`
- Scraping orchestrator + providers: `trackanything-admin/app/services/scraping/orchestrator.py`, `trackanything-admin/app/services/scraping/providers/*`
- AI tools + agent: `trackanything-admin/app/services/ai/agent.py`, `trackanything-admin/app/services/ai/tools/*`
- Frontend flows: `trackanything-app/src/components/*`, `trackanything-app/src/app/[locale]/dashboard/*`
- Database schema & migrations: `trackanything-admin/migrations/*.sql`

