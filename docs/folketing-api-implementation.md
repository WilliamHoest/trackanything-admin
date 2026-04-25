# Folketing API — Implementeringsplan

## Formål

Trackere lovgivningsaktivitet relevant for danske fonde ved at integrere mod Folketingets åbne API (`oda.ft.dk`). Dette er platformens primære differentiator — ingen konkurrenter tilbyder lovgivningstracking for fondsektoren.

---

## API Overblik

**Base URL:** `https://oda.ft.dk/api/`  
**Format:** OData JSON (ingen API-nøgle kræves)  
**Docs:** `https://oda.ft.dk/`

### Relevante endpoints

| Endpoint | Indhold |
|---|---|
| `/Sag` | Lovforslag, beslutningsforslag, forespørgsler |
| `/Dokument` | Tilknyttede dokumenter til sager |
| `/Afstemning` | Afstemningsresultater |
| `/Aktør` | Politikere og udvalg |
| `/Møde` | Udvalgsmøder og dagsordenspunkter |

### Udvalg der skal trackes

| Udvalg | Kode | Relevante keywords |
|---|---|---|
| Erhvervsudvalget | ERU | erhvervsfondsloven, lov om erhvervsdrivende fonde, anbefalinger for god fondsledelse |
| Retsudvalget | REU | fondsloven, fondsudvalget, fondsbetænkning, lov om fonde og visse foreninger |
| Skatteudvalget | SAU | fondsbeskatningsloven, uddelingsfradrag, konsolideringsfradrag |

---

## Datamodel

En Folketing-mention skal mappe til det eksisterende mentions-schema:

```python
{
    "title": str,          # Sagens titel / dokumentets titel
    "link": str,           # URL til sagen på ft.dk
    "content_teaser": str, # Kort beskrivelse / resume
    "platform": str,       # "Folketinget" eller "Folketing - ERU" osv.
    "published_parsed": time.struct_time,  # Fremsættelsesdato eller mødedato
}
```

---

## Implementeringsplan

### Fase 1 — Ny provider: `folketing.py`

**Placering:** `app/services/scraping/providers/folketing.py`

**Arkitektur:** Tre parallelle queries mod OData API — ét per udvalg — filtreret på keywords og dato.

#### Query-struktur (OData)

Søg i sager der er behandlet i et specifikt udvalg:

```
GET /api/Sag?$filter=
  Statsminister ne null
  and DatoFra ge 2026-01-01
  and (
    contains(Titel, 'erhvervsfondsloven')
    or contains(Titel, 'fondsbeskatningsloven')
  )
&$select=id,Titel,Resume,DatoFra,typeid
&$top=50
&$orderby=DatoFra desc
```

Hent dokumenter tilknyttet et møde i et specifikt udvalg:

```
GET /api/Dokument?$filter=
  sagid eq {sag_id}
&$select=id,titel,opdateringsdato,filurl_pdf,filurl_html
```

#### Udvalg-til-sag mapping

Folketing API'et linker sager til udvalg via `Sagstrin`:

```
GET /api/Sagstrin?$filter=
  UdvalgId eq {udvalg_id}
  and opdateringsdato ge 2026-01-01
&$expand=Sag($select=id,Titel,Resume,DatoFra)
&$top=100
```

Udvalgs-IDs (skal verificeres mod live API):
- ERU: `Id eq 30` (verificer)
- REU: `Id eq 32` (verificer)
- SAU: `Id eq 40` (verificer)

**Verificer ID'er:**
```bash
curl "https://oda.ft.dk/api/Udvalg?\$filter=contains(Navn,'Erhverv')&\$select=Id,Navn"
```

#### Keyword-filter strategi

Folketing-sager har ofte teknisk juridisk sprog. I stedet for keyword-matching mod brugerens fond-keywords, filtrerer vi på **faste lovgivnings-keywords** per udvalg (se tabellen ovenfor). Matches returneres til alle brugere med en "Lovgivning"-topic.

Alternativt (mere avanceret): match mod brugerens egne keywords for at kun returnere relevante sager per fond.

---

### Fase 2 — Settings & toggle

Tilføj i `app/core/config.py`:

```python
scraping_provider_folketing_enabled: bool = True
folketing_lookback_days: int = 7  # Lovgivning ændres ikke dagligt
```

Tilføj i `.env`:

```
SCRAPING_PROVIDER_FOLKETING_ENABLED=true
FOLKETING_LOOKBACK_DAYS=7
```

---

### Fase 3 — Registrering i orkestratoren

I `orchestrator.py`, tilføj efter de øvrige providers:

```python
from app.services.scraping.providers.folketing import scrape_folketing

if settings.scraping_provider_folketing_enabled:
    enabled_providers.append((
        "folketing",
        "Folketing",
        scrape_folketing(
            keywords=sanitized_keywords,
            from_date=from_date,
            scrape_run_id=scrape_run_id,
        ),
    ))
```

---

### Fase 4 — Platform i databasen

Tilføj "Folketing" som platform i `platforms`-tabellen:

```sql
INSERT INTO platforms (name) VALUES ('Folketing') ON CONFLICT DO NOTHING;
```

---

## Tekniske overvejelser

### Rate limiting
Folketing API har ingen dokumenteret rate limit, men vær konservativ: max 1 request/sek. Brug `asyncio.sleep(1)` mellem requests.

### Paginering
OData bruger `$top` og `$skip`. Default page size er 20. Brug `$top=100` og paginer hvis nødvendigt.

### Datohåndtering
API returnerer datoer som ISO 8601 strings: `"2026-04-15T00:00:00"`. `parse_mention_date` håndterer dette direkte.

### Links til ft.dk
Sager linkes som: `https://www.ft.dk/samling/20251/lovforslag/l{sagsnummer}/index.htm`  
Dokumenter linkes via `filurl_html` feltet i Dokument-objektet.

### Ingen keyword-afhængighed
I modsætning til de øvrige providers kræver Folketing-provider ikke at brugerens keywords matcher. Den tracker altid de faste lovgivnings-keywords per udvalg og returnerer alt relevant. Mentions tildeles en dedikeret "Lovgivning"-topic automatisk — eller bruger kan oprette en Brand "Lovgivning" med de tre udvalg som topics.

---

## Estimeret arbejde

| Opgave | Tid |
|---|---|
| Verificer udvalgs-IDs mod live API | 30 min |
| Byg `folketing.py` provider | 3-4 timer |
| Test mod live data | 1 time |
| Tilføj platform i DB + settings | 30 min |
| **Total** | **~1 dag** |

---

## Næste skridt

1. Verificer udvalgs-IDs: `curl "https://oda.ft.dk/api/Udvalg?\$select=Id,Navn"`
2. Test OData queries manuelt i browser
3. Implementer `folketing.py` med de tre udvalg
4. Opret "Lovgivning" brand + topics i UI som test
