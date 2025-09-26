# TrackAnything Admin Backend

TrackAnything er et avanceret medieovervågnings-værktøj der kontinuerligt scraper nyhedssider og andre kilder for at finde medieomtaler baseret på specifikke keywords for forskellige kunder. Dette repository indeholder backend API'en for admin-dashboardet.

## 🚀 Funktionalitet

### Core Features

- **Medieovervågning**: Automatisk scraping af mentions fra fire datakilder:
  - **GNews API**: Professionelle nyhedskilder med dansk sprogfokus
  - **SerpAPI**: Google News resultater via API
  - **Politiken**: Direkte web scraping af dansk nyhedssite  
  - **DR**: RSS feeds fra Danmarks Radio
- **Brand Management**: Opret og administrer brands med tilhørende topics og keywords
- **Keyword Management**: Fuld CRUD funktionalitet for keywords
- **Mention Management**: Komplet REST API til at administrere mentions
- **Mention Tracking**: Spor og kategoriser medieomtaler med read/unread og notification status
- **Digest System**: Automatisk generering af sammenfatninger af mentions
- **AI-Powered Chat**: "Atlas Intelligence" - AI-assistent der giver insights baseret på mention data

### AI Chat (Atlas Intelligence)

Atlas chatten giver brugerne mulighed for at have intelligente samtaler med deres data:

- Analysere sentiment i seneste omtaler
- Opsummere vigtige pointer fra specifikke perioder
- Generere udkast til svar på artikler
- Identificere trends og mønstre i mention data

### API Endpoints

- `/api/v1/brands/` - Brand management
- `/api/v1/topics/` - Topic og keyword management
- `/api/v1/keywords/` - Keyword management (CRUD operations)
- `/api/v1/mentions/` - Mention management og viewing (CRUD operations)
- `/api/v1/scraping/` - Scraping funktionalitet (GNews, SerpAPI, Politiken, DR)
- `/api/v1/digests/` - Digest generering
- `/api/v1/chat/` - AI chat funktionalitet
- `/api/v1/users/` - User authentication

## 📋 Forudsætninger

- Python 3.8+
- PostgreSQL database
- Supabase account
- DeepSeek API key (for AI chat funktionalitet)
- GNews API key (for news scraping)
- SerpAPI key (for Google News scraping)
- Visual Studio Code (anbefalet)

## 🛠️ Installation & Setup

### 0. Opsætning for Begyndere (macOS)

#### Installer Python

Hvis du ikke har Python installeret endnu:

**Option 1: Via Homebrew (Anbefalet)**

```bash
# Installer Homebrew hvis du ikke har det:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Installer Python
brew install python
```

**Option 2: Fra Python.org**

1. Gå til [python.org/downloads](https://www.python.org/downloads/)
2. Download den nyeste Python 3.x version for macOS
3. Kør installeren og følg instruktionerne

**Check Python Installation:**

```bash
# Tjek at Python er installeret
python3 --version
# Skal vise noget som: Python 3.x.x

# Tjek pip (package manager)
pip3 --version
```

**Installer Python Extension:**

1. Åbn VS Code
2. Klik på Extensions ikonet i venstre sidebar (□ symbol)
3. Søg efter "Python"
4. Installer "Python" extensionen fra Microsoft

**Åbn Projekt i VS Code:**

```bash
# Naviger til projekt mappen i Terminal
cd /path/to/trackanything-admin

# Åbn projektet i VS Code
code .
```

### 1. Clone Repository

```bash
git clone <repository-url>
cd trackanything-admin
```

### 2. Virtual Environment Setup (Anbefalet)

#### Opret virtual environment:

```bash
# Naviger til projekt-mappen
cd /path/to/trackanything-admin

# Opret virtual environment
python -m venv venv

# Aktiver virtual environment
# På macOS/Linux:
source venv/bin/activate

# På Windows:
venv\\Scripts\\activate
```

#### Når virtual environment er aktiveret:

```bash
# Install dependencies
pip install -r requirements.txt
```

#### Deaktiver virtual environment når du er færdig:

```bash
deactivate
```

**💡 Tips**: Næste gang du skal arbejde på projektet, skal du bare aktivere virtual environment igen:

```bash
source venv/bin/activate  # macOS/Linux
# eller
venv\\Scripts\\activate   # Windows
```

### 3. Environment Variables

Opret eller opdater din `.env` fil i projektets root med følgende:

```env
# Supabase
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key

# Database
DATABASE_URL=postgresql://username:password@host:port/database_name

# AI Chat
DEEPSEEK_API_KEY=your_deepseek_api_key

# News Scraping APIs
GNEWS_API_KEY=your_gnews_api_key
SERPAPI_KEY=your_serpapi_key

# Server Config
DEBUG=true
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

### 4. Database Setup

Kør database schema fra `create_database_schema.sql`:

```bash
# Connect til din PostgreSQL database og kør:
psql -h your_host -U your_username -d your_database -f create_database_schema.sql
```

### 5. Start Development Server

Med virtual environment aktiveret:

```bash
# Start serveren
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Eller alternativt:
python app/main.py
```

Serveren starter på `http://localhost:8000`

## 📚 API Dokumentation

Når serveren kører, kan du tilgå:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **Health Check**: `http://localhost:8000/health`
- **Dev Info**: `http://localhost:8000/dev-info`

## 🔐 Authentication

### Development Mode

Når `DEBUG=true` i `.env`, bruger API'en development authentication:

- Ingen login påkrævet
- Bruger mock user: `madsrunge@hotmail.dk`
- User ID: `db186e82-e79c-45c8-bb4a-0261712e269c`

### Production Mode

Når `DEBUG=false`, kræves ægte Supabase JWT tokens via Bearer authentication.

## 🤖 AI Chat Usage

### Streaming Endpoint

```bash
POST /api/v1/chat/stream
Content-Type: application/json
Authorization: Bearer <token> # Kun i production

{
  "message": "Hvad er den overordnede stemning i mine seneste omtaler?",
  "conversation_history": [
    {"role": "user", "content": "Hej Atlas"},
    {"role": "assistant", "content": "Hej! Jeg er Atlas, din AI intelligence assistent..."}
  ]
}
```

### Non-Streaming Endpoint

```bash
POST /api/v1/chat/
# Samme format som streaming, men returnerer komplet response
```

## 🗂️ Projekt Struktur

```
trackanything-admin/
├── app/
│   ├── api/
│   │   ├── endpoints/          # API endpoint implementations
│   │   └── api_v1.py          # API router config
│   ├── core/
│   │   ├── config.py          # Settings og environment config
│   │   ├── database.py        # Database connection
│   │   └── supabase_client.py # Supabase client
│   ├── crud/
│   │   └── crud.py            # Database operations
│   ├── models/
│   │   └── models.py          # SQLAlchemy models
│   ├── schemas/
│   │   └── *.py               # Pydantic schemas
│   ├── security/
│   │   ├── auth.py            # Production authentication
│   │   └── dev_auth.py        # Development authentication
│   ├── services/
│   │   ├── ai_service.py      # AI chat service
│   │   ├── digest_service.py  # Digest functionality
│   │   └── scraping_service.py # Scraping functionality
│   └── main.py                # FastAPI app
├── requirements.txt           # Python dependencies
├── create_database_schema.sql # Database schema
└── .env                      # Environment variables
```

## 🔧 Development Tips

### Virtual Environment Best Practices

1. **Altid brug virtual environment** for at undgå konflikter mellem projekter
2. **Aktiver environment** før du installerer nye pakker
3. **Freeze dependencies** når du tilføjer nye pakker:
   ```bash
   pip freeze > requirements.txt
   ```

### Database Migrations

Når du ændrer models, skal du opdatere database schemaet manuelt eller bruge migration tools.

### Debugging

- Check `/dev-info` endpoint for at se auth mode og debug status
- I development mode kræves ingen authentication
- Check logs for detaljerede fejlbeskeder

### Environment Management

- Hold `.env` filen sikker og commit den ALDRIG til git
- Brug forskellige `.env` filer til development/production
- Test altid med `DEBUG=false` før deployment

## 📞 Support

For spørgsmål eller problemer, kontakt udviklerteamet eller opret et issue i repository.
