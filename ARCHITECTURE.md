# TrackAnything Admin Backend - System Arkitektur v3.0

Dette dokument beskriver arkitekturen, design patterns og development guidelines for TrackAnything Admin Backend. Læs dette dokument før du implementerer nye features.

## 🏗️ Overordnet Arkitektur

TrackAnything Admin Backend følger **Clean Architecture** principper med **Supabase REST API** som database layer og FastAPI som web framework.

### Core Layers

```
├── API Layer          # FastAPI endpoints og request/response handling
├── Service Layer       # Business logic og external API calls  
├── CRUD Layer         # Supabase REST API operations
├── Schema Layer       # Pydantic validation og serialization
└── Core Layer         # Configuration, Supabase client, utilities
```

## 📁 Detailed Folder Structure

```
app/
├── api/
│   ├── api_v1.py              # Main API router - registrerer alle endpoints
│   └── endpoints/             # Individual endpoint implementations
│       ├── brands_supabase.py      # Brand management endpoints
│       ├── topics_supabase.py      # Topic/keyword management
│       ├── keywords_supabase.py    # Keyword CRUD operations
│       ├── mentions_supabase.py    # Mention management og viewing
│       ├── users_supabase.py       # User profile endpoints
│       ├── scraping_supabase.py    # Scraping functionality (GNews, SerpAPI, Politiken, DR)
│       ├── digests_supabase.py     # Digest generation og webhook sending
│       └── chat_supabase.py        # AI chat functionality
├── core/
│   ├── config.py              # Settings og environment configuration
│   ├── supabase_client.py     # Supabase client initialization
│   └── supabase_db.py         # Supabase CRUD dependency injection
├── crud/
│   └── supabase_crud.py       # Supabase REST API operations (Create, Read, Update, Delete)
├── schemas/
│   ├── brand.py               # Pydantic schemas for brand endpoints
│   ├── topic.py               # Pydantic schemas for topic endpoints
│   ├── mention.py             # Pydantic schemas for mention data
│   ├── profile.py             # User profile schemas
│   └── ...                    # Other domain-specific schemas
├── security/
│   ├── auth.py                # Production authentication with Supabase
│   └── dev_auth.py            # Development authentication (mock user)
├── services/
│   ├── ai_service.py          # AI chat business logic
│   ├── digest_service_supabase.py  # Digest generation logic med Supabase
│   └── scraping_service.py    # Multi-source scraping (GNews API, SerpAPI, Politiken, DR)
└── main.py                    # FastAPI application setup
```

## 🧩 Separation of Concerns

### 1. API Layer (`/api/endpoints/`)
**Ansvar**: HTTP request/response handling, input validation, authentication
```python
# Kun ansvarlig for:
- Route definitions (@router.get, @router.post, etc.)
- Request/response models (Pydantic schemas)
- Authentication dependency injection
- HTTP status codes og error handling
- Input validation via Pydantic

# Må IKKE:
- Indeholde business logic
- Direkte database operationer (brug SupabaseCRUD)
- Komplekse data transformationer
```

### 2. Service Layer (`/services/`)
**Ansvar**: Business logic, orchestration af CRUD operationer, external API calls
```python
# Ansvarlig for:
- Complex business operations
- Orchestrating multiple Supabase CRUD operations
- External API integrations (DeepSeek, webhooks, scraping sources)
- Data processing og aggregation
- Business rule enforcement

# Eksempel struktur:
async def create_brand_with_topics(crud: SupabaseCRUD, brand_data: BrandCreate, topics: List[str], user_id: UUID):
    # 1. Validate business rules
    # 2. Create brand via Supabase CRUD
    # 3. Create related topics via Supabase CRUD
    # 4. Send notifications if needed
    # 5. Return structured response
```

### 3. CRUD Layer (`/crud/supabase_crud.py`)
**Ansvar**: Supabase REST API operationer, data persistence
```python
# Kun ansvarlig for:
- Supabase table operations (select, insert, update, delete)
- Data filtering og ordering via Supabase queries
- Relationship handling via Supabase joins
- Error handling for API calls

# Må IKKE:
- Business logic
- External API calls (andet end Supabase)
- Complex data transformations
- Authentication checks (håndteres i API layer)

# Eksempel pattern:
async def create_brand(self, brand: BrandCreate, profile_id: UUID) -> Optional[Dict[str, Any]]:
    try:
        data = {
            "name": brand.name,
            "profile_id": str(profile_id),
            "created_at": datetime.utcnow().isoformat()
        }
        result = self.supabase.table("brands").insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"Error creating brand: {e}")
        return None
```

### 4. Schema Layer (`/schemas/`)
**Ansvar**: Data validation, serialization/deserialization
```python
# For hver domain entity, definer:
- Create schema (input til POST endpoints)
- Update schema (input til PUT/PATCH endpoints)  
- Response schema (output fra GET endpoints)
- List/detailed response variants

# Eksempel:
class BrandCreate(BaseModel):
    name: str

class BrandUpdate(BaseModel):
    name: Optional[str] = None

class BrandResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    
    class Config:
        from_attributes = True
```

## 🛠️ FastAPI Development Patterns

### 1. Endpoint Structure
```python
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.supabase_db import get_supabase_crud
from app.crud.supabase_crud import SupabaseCRUD
from app.security.auth import get_current_user

router = APIRouter()

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_resource(
    resource: CreateSchema,
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_current_user)
):
    """
    Clear docstring explaining what this endpoint does
    """
    # 1. Additional validation if needed
    # 2. Call CRUD function
    # 3. Handle potential exceptions
    # 4. Return response
    
    try:
        result = await crud.create_resource(resource, current_user.id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create resource"
            )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
```

### 2. Authentication Pattern
```python
# Development vs Production auth
from app.security.auth import get_current_user
from app.security.dev_auth import get_dev_user
from app.core.config import settings

# Use conditional dependency
get_user = get_dev_user if settings.debug else get_current_user

@router.get("/")
async def protected_endpoint(current_user = Depends(get_user)):
    # Endpoint automatically uses dev auth in DEBUG mode
    pass
```

### 3. Supabase Dependency Pattern
```python
# Altid brug dependency injection for Supabase CRUD
async def endpoint_function(
    crud: SupabaseCRUD = Depends(get_supabase_crud),
    current_user = Depends(get_user)
):
    # Supabase CRUD operations
    result = await crud.get_something(current_user.id)
    return result
```

### 4. Error Handling Pattern
```python
# Konsistent error handling
try:
    result = await crud.some_operation()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )
    return result
except ValueError as e:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Validation error: {str(e)}"
    )
except Exception as e:
    # Log error for debugging
    print(f"Unexpected error: {str(e)}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error"
    )
```

## 🔐 Authentication & Authorization

### Current Implementation
- **Development Mode** (`DEBUG=true`): Mock user authentication
- **Production Mode** (`DEBUG=false`): Supabase JWT token validation

### Authorization Pattern
```python
# Check ownership before operations
async def update_brand(brand_id: int, crud: SupabaseCRUD, current_user):
    # 1. Get resource
    brand = await crud.get_brand(brand_id)
    
    # 2. Check ownership
    if not brand or brand.get("profile_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    # 3. Proceed with operation
    return await crud.update_brand(brand_id, updates, current_user.id)
```

## 🗄️ Supabase Patterns

### CRUD Operations
```python
# Standard Supabase CRUD pattern
async def get_entity(self, entity_id: int) -> Optional[Dict[str, Any]]:
    try:
        result = self.supabase.table("entities").select("*").eq("id", entity_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"Error getting entity: {e}")
        return None

async def get_entities_by_user(self, user_id: UUID) -> List[Dict[str, Any]]:
    try:
        result = self.supabase.table("entities").select("*").eq("profile_id", str(user_id)).execute()
        return result.data or []
    except Exception as e:
        print(f"Error getting entities by user: {e}")
        return []

async def create_entity(self, entity: EntityCreateSchema, user_id: UUID) -> Optional[Dict[str, Any]]:
    try:
        data = {
            **entity.model_dump(),
            "profile_id": str(user_id),
            "created_at": datetime.utcnow().isoformat()
        }
        result = self.supabase.table("entities").insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"Error creating entity: {e}")
        return None
```

### Query Optimization
```python
# Use Supabase joins for relationships
async def get_brand_with_topics(self, brand_id: int):
    try:
        result = self.supabase.table("brands").select("""
            *,
            topics(*)
        """).eq("id", brand_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"Error getting brand with topics: {e}")
        return None
```

## 🚀 Guidelines for New Features

### 1. Planning Phase
1. **Define Data Structure**: Hvilke Supabase tables skal du bruge?
2. **Design API Contract**: Hvilke endpoints skal du bruge?
3. **Identify Business Logic**: Hvad er business rules og workflows?

### 2. Implementation Order
```
1. Schemas (Pydantic) - Input/output validation  
2. CRUD operations - Supabase REST API calls
3. Services - Business logic layer (hvis nødvendigt)
4. API endpoints - HTTP interface
5. Tests - Validation af functionality
```

### 3. Feature Implementation Checklist

**Schemas (`/schemas/`)**
- [ ] Create separate file for domain (e.g., `new_feature.py`)
- [ ] Define Create, Update, Response schemas
- [ ] Add proper validation rules

**CRUD (`/crud/supabase_crud.py`)**
- [ ] Add new methods to SupabaseCRUD class
- [ ] Implement basic CRUD operations via Supabase REST API
- [ ] Add user-specific queries (filter by profile_id)
- [ ] Include relationship loading where needed
- [ ] Add proper error handling

**Services (`/services/`)**
- [ ] Create service file if complex business logic
- [ ] Handle external API integrations
- [ ] Implement business rule validation
- [ ] Use async/await patterns

**API Endpoints (`/api/endpoints/`)**
- [ ] Create new `{feature}_supabase.py` file
- [ ] Implement all necessary endpoints (GET, POST, PUT, DELETE)
- [ ] Add proper authentication via get_user dependency
- [ ] Use SupabaseCRUD dependency injection
- [ ] Include comprehensive docstrings
- [ ] Add ownership validation

**Integration (`/api/api_v1.py`)**
- [ ] Import new endpoint module
- [ ] Register new router in main API router
- [ ] Add appropriate prefix og tags

### 4. Code Quality Standards

**Naming Conventions**
- Functions: snake_case (e.g., `get_user_brands`, `create_mention`)
- Variables: snake_case
- Constants: UPPER_SNAKE_CASE
- Files: snake_case with `_supabase.py` suffix for endpoints

**Documentation**
- All public functions skal have docstrings
- Complex business logic skal være kommenteret
- API endpoints skal have beskrivende descriptions

**Error Handling**
- Brug appropriate HTTP status codes
- Provide descriptive error messages
- Log errors for debugging (men ikke sensitive data)
- Always handle Supabase exceptions gracefully

## 📊 Current API Endpoints

### Core Resources
- **Brands** (`/api/v1/brands/`): Brand management med CRUD operations
- **Topics** (`/api/v1/topics/`): Topic management med keyword associations
- **Keywords** (`/api/v1/keywords/`): Keyword CRUD operations
- **Mentions** (`/api/v1/mentions/`): Komplet mention management med filtrering
- **Users** (`/api/v1/users/`): User profile management

### Functionality Endpoints  
- **Scraping** (`/api/v1/scraping/`): Multi-source data collection (GNews, SerpAPI, Politiken, DR)
- **Digests** (`/api/v1/digests/`): Automated mention summarization og webhook delivery
- **Chat** (`/api/v1/chat/`): AI-powered insights og analytics

### Data Sources Integration
- **GNews API**: Professional news sources med dansk sprogfokus
- **SerpAPI**: Google News resultater via structured API  
- **Politiken**: Direct web scraping af danske artikler
- **DR RSS**: Danmarks Radio news feeds
- **Deduplication**: Automatic URL-based duplicate removal på tværs af alle kilder

### Mention Management Features
- **Filtering**: Brand, topic, platform, read status, notification status
- **Pagination**: Skip/limit support for store datasæt
- **Status tracking**: Read/unread og notification status management
- **Batch operations**: Convenience endpoints for status updates
- **Full CRUD**: Create, read, update, delete mentions

## 🧪 Testing Strategy

### Test Structure
```
tests/
├── test_supabase_crud.py    # Supabase CRUD operations tests
├── test_services.py         # Business logic tests  
├── test_endpoints.py        # API integration tests
└── conftest.py             # Test configuration og fixtures
```

### Test Patterns
```python
# Use pytest fixtures for Supabase setup
@pytest.fixture
def supabase_crud():
    return SupabaseCRUD()

# Test CRUD operations
@pytest.mark.asyncio
async def test_create_brand(supabase_crud):
    brand_data = BrandCreate(name="Test Brand")
    result = await supabase_crud.create_brand(brand_data, user_id)
    assert result["name"] == "Test Brand"

# Test API endpoints
def test_create_brand_endpoint(client, auth_headers):
    response = client.post("/api/v1/brands/", 
                          json={"name": "Test Brand"}, 
                          headers=auth_headers)
    assert response.status_code == 201
```

## 🔄 Development Workflow

1. **Start med data design** - Planlæg Supabase table structure
2. **Define API contract** - Schemas og endpoint signatures  
3. **Implement CRUD layer** - Supabase REST API operations
4. **Add business logic** - Services layer hvis nødvendig
5. **Connect HTTP layer** - API endpoints
6. **Test thoroughly** - Unit og integration tests
7. **Update documentation** - API docs og architecture notes

## 🚨 Common Anti-Patterns to Avoid

❌ **Don't put business logic in API endpoints**
❌ **Don't put HTTP concerns in CRUD functions**  
❌ **Don't skip authentication checks**
❌ **Don't return raw Supabase responses without validation**
❌ **Don't hardcode configuration values**
❌ **Don't ignore error handling**
❌ **Don't forget to validate user ownership of resources**
❌ **Don't use synchronous operations (always use async/await)**

✅ **Do follow the layered architecture**
✅ **Do use dependency injection**
✅ **Do validate all input data**
✅ **Do handle errors gracefully**
✅ **Do write comprehensive tests**
✅ **Do document your code**
✅ **Do use async/await for all Supabase operations**

## 🎯 Supabase Best Practices

### Query Optimization
- Use `select()` to specify only needed fields
- Use `single()` for single record queries
- Use proper filtering with `eq()`, `in_()`, etc.
- Use `order()` for consistent sorting

### Error Handling
```python
try:
    result = self.supabase.table("table").operation().execute()
    return result.data
except Exception as e:
    print(f"Supabase operation failed: {e}")
    return None
```

### Relationship Handling
```python
# Use nested selects for relationships
result = self.supabase.table("brands").select("""
    *,
    topics(*, keywords(*)),
    profile:profiles(*)
""").execute()
```

## 📋 Migration Notes

### From SQLAlchemy to Supabase REST API (v2.0 → v3.0)

**Completed Changes:**
- ✅ Replaced all SQLAlchemy ORM models with Supabase REST API calls
- ✅ Converted all endpoints to use `SupabaseCRUD` dependency injection
- ✅ Removed `database.py`, `models/`, and `crud/` (SQLAlchemy files)
- ✅ Updated `requirements.txt` to remove SQLAlchemy dependencies
- ✅ All endpoints now use `async/await` pattern
- ✅ Consistent error handling across all operations

**Benefits Achieved:**
- 🚀 No more network/port issues (uses HTTPS instead of PostgreSQL port 5432)
- 📈 Better performance via Supabase connection pooling
- 🔄 Auto-scaling database operations
- 🎯 Simplified architecture with fewer dependencies
- 🛡️ Built-in Row Level Security support

---

*Dette dokument er opdateret til v3.0 arkitekturen med 100% Supabase REST API implementation.*