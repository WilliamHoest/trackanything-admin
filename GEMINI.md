# TrackAnything Admin Backend

## Project Overview

**TrackAnything Admin** is the backend service for the TrackAnything media monitoring platform. It is built with **Python** and **FastAPI**, serving as the central hub for data scraping, management, and intelligence.

**Core Responsibilities:**
*   **Media Scraping:** Orchestrates scraping from multiple sources (GNews, SerpAPI, Politiken, DR) to track mentions based on user-defined keywords.
*   **Data Management:** Manages the hierarchy of Brands -> Topics -> Keywords and stores mentions via Supabase.
*   **AI Intelligence:** Powers "Atlas Intelligence", a chat interface for analyzing sentiment and summarizing mentions (using DeepSeek).
*   **API Service:** Provides a RESTful API for the frontend application (`trackanything-app`).

**Key Technologies:**
*   **Framework:** FastAPI
*   **Server:** Uvicorn
*   **Database:** Supabase (PostgreSQL + REST API)
*   **Validation:** Pydantic
*   **Scraping:** BeautifulSoup4, lxml, feedparser
*   **Authentication:** Supabase Auth (JWT) / Mock Auth (Dev)

## Architecture

The project follows a **Clean Architecture** pattern, strictly separating concerns:

```
app/
├── api/            # Interface Layer: HTTP endpoints, request handling.
│   ├── endpoints/  # Individual route modules (e.g., brands, mentions).
│   └── api_v1.py   # Router aggregation.
├── services/       # Business Logic Layer: Complex logic, external APIs (AI, Scraping).
├── crud/           # Data Access Layer: Direct Supabase interactions (SupabaseCRUD).
├── schemas/        # Domain Layer: Pydantic models for data validation and API contracts.
└── core/           # Infrastructure: Config, Database clients, Authentication.
```

### Key Concepts
*   **Brand-Scoped Scraping:** Data is organized hierarchically: `User -> Brand -> Topic -> Keyword`. Scraping aggregates keywords from active topics to query sources.
*   **Supabase-First:** All persistence is handled via the Supabase Python client. There is no local database instance managed by the app itself; it relies on the managed Supabase instance.
*   **Mock Authentication:** In development (`DEBUG=true`), authentication is bypassed using a mock user to simplify testing.

## Building and Running

### Prerequisites
*   Python 3.8+
*   Supabase Account & Project
*   API Keys (DeepSeek, GNews, SerpAPI)

### Setup

1.  **Create Virtual Environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # macOS/Linux
    # venv\Scripts\activate   # Windows
    ```

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configuration:**
    Create a `.env` file in the root directory (see `.env.example` if available, or reference below):
    ```env
    SUPABASE_URL=your_url
    SUPABASE_KEY=your_key
    DEEPSEEK_API_KEY=your_key
    GNEWS_API_KEY=your_key
    SERPAPI_KEY=your_key
    DEBUG=true
    ```

### Running the Server

Start the development server with hot-reload:

```bash
python -m uvicorn app.main:app --reload
```

*   **API Docs:** `http://localhost:8000/docs`
*   **Health Check:** `http://localhost:8000/health`

## Development Conventions

*   **Dependency Injection:** Always use `Depends()` for injecting `SupabaseCRUD` and `current_user` into endpoints.
*   **Async/Await:** All I/O bound operations (database, external APIs) must be asynchronous.
*   **Pydantic Schemas:** Use strict schemas for all request bodies and response models. Define them in `app/schemas/`.
*   **CRUD Isolation:** Do not perform DB logic in endpoints. Use `app/crud/supabase_crud.py`.
*   **Service Isolation:** Complex business logic (like scraping orchestration or AI chat) goes into `app/services/`.
*   **Testing:** Run tests using `pytest` (ensure you have a test environment configuration).

## Directory Structure Overview

*   `app/api/endpoints/`: Contains the REST API route handlers.
    *   `brands_supabase.py`, `topics_supabase.py`, etc.: CRUD endpoints.
    *   `scraping_supabase.py`: Triggers for scraping jobs.
    *   `chat_supabase.py`: Endpoints for the AI chat.
*   `app/core/`: Configuration and core utilities.
    *   `config.py`: Environment variable loading.
    *   `supabase_client.py`: Initialization of the Supabase client.
*   `app/crud/supabase_crud.py`: The central class for all database interactions.
*   `app/services/`:
    *   `scraping_service.py`: Logic for fetching data from GNews, SerpAPI, etc.
    *   `ai_service.py`: Interface with DeepSeek API.
    *   `digest_service_supabase.py`: Logic for generating email digests.
*   `migrations/`: SQL scripts for database schema updates (run against Supabase SQL editor).
