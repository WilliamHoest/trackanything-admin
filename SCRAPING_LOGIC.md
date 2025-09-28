# TrackAnything - Scraping Logic & Data Structure

Dette dokument beskriver den fundamentale logik bag TrackAnything's scraping-system og hvordan data struktureres for at give kunder maksimal fleksibilitet og kontrol.

## 🏗️ Koncept: Brand-Scoped Scraping

TrackAnything bruger et **brand-baseret scope system** hvor "brand" fungerer som en logisk container for scraping-konfiguration - ikke nødvendigvis et fysisk brand/virksomhed.

### Core Filosofi
- **Et "brand" = Et scraping scope** (kan være konkurrenter, egen virksomhed, branche-trends, etc.)
- **Topics** = Tematiske kategorier inden for scopet
- **Keywords** = Specifikke søgeord der trigger mentions
- **Fleksibel many-to-many** struktur tillader genbrug og kompleks organisering

## 📊 Data Hierarki

```
Bruger (Profile)
├── Brand 1: "Konkurrenter"              # Scope: Overvågning af konkurrenter
│   ├── Topic: "Prisændringer"
│   │   └── Keywords: ["pris", "rabat", "tilbud", "kampagne"]
│   ├── Topic: "Produktlanceringer" 
│   │   └── Keywords: ["ny model", "lancering", "release"]
│   └── Topic: "Markedsføring"
│       └── Keywords: ["reklame", "commercial", "sponsorering"]
│
├── Brand 2: "Egen virksomhed"           # Scope: Monitoring af egen omtale
│   ├── Topic: "Presseomtale"
│   │   └── Keywords: ["MinVirksomhed", "CEO Navn", "produktnavn"]
│   ├── Topic: "Kundetilfredshed"
│   │   └── Keywords: ["anmeldelse", "rating", "erfaring med"]
│   └── Topic: "Krisestyring"
│       └── Keywords: ["klage", "fejl", "problem", "utilfreds"]
│
├── Brand 3: "Branche Trends"            # Scope: Branche-intelligence
│   ├── Topic: "Teknologi"
│   │   └── Keywords: ["AI", "blockchain", "automation"]
│   ├── Topic: "Regulering"
│   │   └── Keywords: ["GDPR", "lovgivning", "regler"]
│   └── Topic: "Market Intelligence"
│       └── Keywords: ["markedsandel", "vækst", "investment"]
│
└── Brand 4: "Event Monitoring"          # Scope: Specifik event/kampagne
    └── Topic: "Produktlancering Q1"
        └── Keywords: ["Product X", "launch event", "ny innovation"]
```

## 🔍 Scraping Workflow

### 1. Keyword Aggregation
```python
# Systemet samler ALLE keywords fra brugerens aktive topics
def get_user_keywords(profile_id: UUID) -> List[str]:
    # Henter alle keywords fra:
    # - Alle brands tilhørende brugeren
    # - Alle aktive topics under disse brands  
    # - Alle keywords tilknyttet disse topics
    return consolidated_keywords
```

### 2. Multi-Source Scraping
```python
# Alle keywords sendes til alle 4 kilder samtidig:
gnews_articles = fetch_gnews_articles(all_keywords)      # GNews API
serpapi_articles = fetch_serpapi_articles(all_keywords)   # SerpAPI  
politiken_articles = crawl_politiken(all_keywords)        # Politiken scraping
dr_articles = crawl_dr(all_keywords)                      # DR RSS feeds
```

### 3. Intelligent Matching & Storage
- **Keyword matching** sker i titel + beskrivelse af artikler
- **Deduplication** baseret på normalized URLs på tværs af kilder
- **Mentions gemmes** med reference til specifik brand+topic for præcis kategorisering

## 🎯 Kunde Use Cases

### Use Case 1: Konkurrence-intelligence
```
Brand: "Konkurrent Overvågning"
├── Topic: "Priser" → Keywords: ["pris", "rabat", "tilbud"]
├── Topic: "Produkter" → Keywords: ["ny model", "feature"]  
└── Topic: "Marketing" → Keywords: ["kampagne", "reklame"]

Resultat: Kunden får alle mentions om konkurrenters aktiviteter
```

### Use Case 2: Egen Brand Monitoring  
```
Brand: "Virksomhed A Monitoring"
├── Topic: "Presseomtale" → Keywords: ["Virksomhed A", "CEO navn"]
├── Topic: "Produktomtale" → Keywords: ["Produkt X", "service Y"]
└── Topic: "Krisestyring" → Keywords: ["klage", "problem"]

Resultat: Komplet overblik over virksomhedens omtale
```

### Use Case 3: Multi-Brand Portfolio
```
Brand: "Portfolio Virksomhed 1" → Keywords: [...]
Brand: "Portfolio Virksomhed 2" → Keywords: [...]  
Brand: "Portfolio Virksomhed 3" → Keywords: [...]

Resultat: Samlet dashboard for alle virksomheder
```

### Use Case 4: Event/Campaign Monitoring
```
Brand: "Black Friday Campaign 2024"
└── Topic: "Campaign Performance" → Keywords: ["black friday", "kampagne navn"]

Resultat: Tidsbegrænset monitoring af specifik kampagne
```

## 🔧 Tekniske Fordele

### 1. Skalerbarhed
- **Efficient scraping**: Alle keywords sendes i batch til hver kilde
- **Smart deduplication**: Undgår dubletter på tværs af kilder
- **Parallel processing**: Alle 4 kilder scrapes samtidig

### 2. Fleksibilitet  
- **Many-to-many**: Keywords kan genbruges på tværs af topics
- **Granulær kontrol**: Topics kan aktiveres/deaktiveres individuelt
- **Dynamic scoping**: Kunder kan nemt reorganisere deres struktur

### 3. Performance
- **Single scraping run**: Henter data for alle brugerens scopes på én gang
- **Intelligent filtering**: Mentions kategoriseres automatisk til korrekt brand+topic
- **Optimized queries**: Database struktur supporterer effektive joins

## 📅 Scheduling & Automation

### Nuværende Implementation
```python
# Daglig scraping klokken 09:00
@cron("0 9 * * *")
async def daily_scraping():
    for profile in get_active_profiles():
        keywords = get_all_user_keywords(profile.id)
        mentions = fetch_all_mentions(keywords)
        categorize_and_store_mentions(mentions, profile.id)
```

### Fremtidige Muligheder
- **Custom scheduling**: Forskellige brands kan scrapes på forskellige tider
- **Frequency control**: Nogle scopes kunne køre oftere end andre
- **Alert thresholds**: Automatiske notifikationer ved høj aktivitet

## 💡 Best Practices for Kunder

### 1. Brand Naming
- **Beskrivende navne**: "Konkurrenter Q1", "Egen Brand", "Branche Trends"
- **Tidsspecifikt**: "Campaign Oktober", "Launch Event"
- **Funktionelt**: "Crisis Monitoring", "Competitive Intel"

### 2. Topic Organization
- **Tematisk opdeling**: Separate topics for forskellige formål
- **Granularitet**: Balance mellem specificitet og overskuelighed  
- **Aktivitetstatus**: Brug is_active til midlertidig deaktivering

### 3. Keyword Strategy
- **Variation**: Inkluder synonymer og alternative stavemåder
- **Specificitet**: Balance mellem brede og specifikke termer
- **Genbrug**: Samme keyword kan bruges i multiple topics

## 🚀 Fremtidige Optimeringsmuligheder

### 1. Intelligent Keyword Expansion
- **Synonym detection**: Automatisk forslag til relaterede keywords
- **Trend analysis**: Identificer nye relevante søgeord baseret på mentions
- **ML-powered suggestions**: AI-drevne keyword anbefalinger

### 2. Advanced Filtering
- **Sentiment-based routing**: Automatically categorize mentions by sentiment
- **Source prioritization**: Weight certain news sources higher
- **Language detection**: Filter mentions by language

### 3. Dynamic Scoping
- **Auto-archiving**: Automatically deactivate old campaigns/events
- **Performance analytics**: Track which keywords generate most relevant mentions
- **ROI optimization**: Suggest keyword optimizations based on mention quality

## 📋 Implementation Checklist

Når du udvider scraping-funktionaliteten, husk at:

- [ ] **Bevare brand-scope logikken** som foundation
- [ ] **Teste keyword aggregation** på tværs af alle brands/topics  
- [ ] **Validere mention categorization** til korrekt brand+topic
- [ ] **Optimere for performance** ved store keyword-sæt
- [ ] **Dokumentere nye funktioner** i relation til brand-scope konceptet

---

*Dette dokument fungerer som living documentation - opdater det når scraping-logikken udvikles eller optimeres.*