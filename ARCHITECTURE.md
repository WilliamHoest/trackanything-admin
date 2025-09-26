# TrackAnything Admin Backend - System Arkitektur

Dette dokument beskriver arkitekturen, design patterns og development guidelines for TrackAnything Admin Backend. Læs dette dokument før du implementerer nye features.

## 🏗️ Overordnet Arkitektur

TrackAnything Admin Backend følger **Clean Architecture** og **Domain-Driven Design** principper med FastAPI som web framework.

### Core Layers

```
├── API Layer          # FastAPI endpoints og request/response handling
├── Service Layer       # Business logic og orchestration  
├── CRUD Layer         # Database operationer og queries
├── Model Layer        # SQLAlchemy database models
├── Schema Layer       # Pydantic validation og serialization
└── Core Layer         # Configuration, database connection, utilities
```

## 📁 Detailed Folder Structure

```
app/
├── api/
│   ├── api_v1.py              # Main API router - registrerer alle endpoints
│   └── endpoints/             # Individual endpoint implementations
│       ├── brands.py          # Brand management endpoints
│       ├── topics.py          # Topic/keyword management
│       ├── users.py           # Authentication endpoints
│       ├── scraping.py        # Scraping functionality
│       ├── digests.py         # Digest generation
│       └── chat.py            # AI chat functionality
├── core/
│   ├── config.py              # Settings og environment configuration
│   ├── database.py            # SQLAlchemy database setup
│   └── supabase_client.py     # Supabase client initialization
├── crud/
│   └── crud.py                # Database operations (Create, Read, Update, Delete)
├── models/
│   └── models.py              # SQLAlchemy ORM models
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
│   ├── digest_service.py      # Digest generation logic
│   └── scraping_service.py    # Scraping orchestration
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
- Direkte database operationer
- Komplekse data transformationer
```

### 2. Service Layer (`/services/`)
**Ansvar**: Business logic, orchestration af CRUD operationer, external API calls
```python
# Ansvarlig for:
- Complex business operations
- Orchestrating multiple CRUD operations
- External API integrations (DeepSeek, webhooks)
- Data processing og aggregation
- Business rule enforcement

# Eksempel struktur:
async def create_brand_with_topics(db: Session, brand_data: BrandCreate, topics: List[str]):
    # 1. Validate business rules
    # 2. Create brand via CRUD
    # 3. Create related topics via CRUD
    # 4. Send notifications if needed
    # 5. Return structured response
```

### 3. CRUD Layer (`/crud/`)
**Ansvar**: Database operationer, simple queries, data persistence
```python
# Kun ansvarlig for:
- SQLAlchemy query operations
- Basic CRUD operations
- Database relationships handling
- Simple data filtering/sorting

# Må IKKE:
- Business logic
- External API calls
- Complex data transformations
- Authentication checks (håndteres i API layer)
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
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.security.auth import get_current_user

router = APIRouter()

@router.post("/", response_model=ResponseSchema, status_code=status.HTTP_201_CREATED)
def create_resource(
    resource: CreateSchema,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Clear docstring explaining what this endpoint does
    """
    # 1. Additional validation if needed
    # 2. Call service layer function
    # 3. Handle potential exceptions
    # 4. Return response
    
    try:
        result = service_function(db, resource, current_user.id)
        return result
    except ValueError as e:
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
def protected_endpoint(current_user = Depends(get_user)):
    # Endpoint automatically uses dev auth in DEBUG mode
    pass
```

### 3. Database Dependency Pattern
```python
# Altid brug dependency injection for database sessions
def endpoint_function(
    db: Session = Depends(get_db),
    current_user = Depends(get_user)
):
    # Database session automatisk managed (åbnet/lukket)
    result = crud.get_something(db, user_id=current_user.id)
    return result
```

### 4. Error Handling Pattern
```python
# Konsistent error handling
try:
    result = some_operation()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )
    return result
except ValidationError as e:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Validation error: {str(e)}"
    )
except Exception as e:
    # Log error for debugging
    logger.error(f"Unexpected error: {str(e)}")
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
def update_brand(brand_id: int, current_user = Depends(get_user)):
    # 1. Get resource
    brand = crud.get_brand(db, brand_id)
    
    # 2. Check ownership
    if not brand or brand.profile_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found"
        )
    
    # 3. Proceed with operation
    return crud.update_brand(db, brand_id, updates)
```

## 🗄️ Database Patterns

### Model Relationships
```python
# Altid definer relationships i begge retninger
class Profile(Base):
    brands = relationship("Brand", back_populates="profile", cascade="all, delete-orphan")

class Brand(Base):
    profile = relationship("Profile", back_populates="brands")
```

### CRUD Operations
```python
# Standard CRUD pattern
def get_entity(db: Session, entity_id: int) -> Optional[EntityModel]:
    return db.query(EntityModel).filter(EntityModel.id == entity_id).first()

def get_entities_by_user(db: Session, user_id: uuid.UUID) -> List[EntityModel]:
    return db.query(EntityModel).filter(EntityModel.user_id == user_id).all()

def create_entity(db: Session, entity: EntityCreateSchema, user_id: uuid.UUID) -> EntityModel:
    db_entity = EntityModel(**entity.model_dump(), user_id=user_id)
    db.add(db_entity)
    db.commit()
    db.refresh(db_entity)
    return db_entity
```

### Query Optimization
```python
# Use joinedload for relationships
from sqlalchemy.orm import joinedload

def get_brand_with_topics(db: Session, brand_id: int):
    return db.query(Brand).options(
        joinedload(Brand.topics)
    ).filter(Brand.id == brand_id).first()
```

## 🚀 Guidelines for New Features

### 1. Planning Phase
1. **Define Domain Model**: Hvad er dine entities og deres relationships?
2. **Design API Contract**: Hvilke endpoints skal du bruge?
3. **Identify Business Logic**: Hvad er business rules og workflows?

### 2. Implementation Order
```
1. Models (SQLAlchemy) - Database structure
2. Schemas (Pydantic) - Input/output validation  
3. CRUD operations - Database layer
4. Services - Business logic layer
5. API endpoints - HTTP interface
6. Tests - Validation af functionality
```

### 3. Feature Implementation Checklist

**Models (`/models/models.py`)**
- [ ] Define SQLAlchemy model with appropriate relationships
- [ ] Add foreign keys og constraints
- [ ] Include timestamps (created_at, updated_at)

**Schemas (`/schemas/`)**
- [ ] Create separate file for domain (e.g., `new_feature.py`)
- [ ] Define Create, Update, Response schemas
- [ ] Add proper validation rules

**CRUD (`/crud/crud.py`)**
- [ ] Implement basic CRUD operations
- [ ] Add user-specific queries (filter by user/profile)
- [ ] Include relationship loading where needed

**Services (`/services/`)**
- [ ] Create service file if complex business logic
- [ ] Handle external API integrations
- [ ] Implement business rule validation

**API Endpoints (`/api/endpoints/`)**
- [ ] Create new router file
- [ ] Implement all necessary endpoints (GET, POST, PUT, DELETE)
- [ ] Add proper authentication
- [ ] Include comprehensive docstrings

**Integration (`/api/api_v1.py`)**
- [ ] Register new router in main API router
- [ ] Add appropriate prefix og tags

### 4. Code Quality Standards

**Naming Conventions**
- Models: PascalCase (e.g., `UserProfile`, `BrandMention`)
- Functions: snake_case (e.g., `get_user_brands`, `create_mention`)
- Variables: snake_case
- Constants: UPPER_SNAKE_CASE

**Documentation**
- All public functions skal have docstrings
- Complex business logic skal være kommenteret
- API endpoints skal have beskrivende descriptions

**Error Handling**
- Brug appropriate HTTP status codes
- Provide descriptive error messages
- Log errors for debugging (men ikke sensitive data)

## 🧪 Testing Strategy

### Test Structure
```
tests/
├── test_crud.py          # Database operations tests
├── test_services.py      # Business logic tests  
├── test_endpoints.py     # API integration tests
└── conftest.py          # Test configuration og fixtures
```

### Test Patterns
```python
# Use pytest fixtures for database setup
@pytest.fixture
def test_db():
    # Setup test database
    yield db
    # Cleanup

# Test CRUD operations
def test_create_brand(test_db):
    brand_data = BrandCreate(name="Test Brand")
    result = crud.create_brand(test_db, brand_data, user_id)
    assert result.name == "Test Brand"

# Test API endpoints
def test_create_brand_endpoint(client, auth_headers):
    response = client.post("/api/v1/brands/", 
                          json={"name": "Test Brand"}, 
                          headers=auth_headers)
    assert response.status_code == 201
```

## 🔄 Development Workflow

1. **Start med database design** - Models først
2. **Define API contract** - Schemas og endpoint signatures  
3. **Implement data layer** - CRUD operations
4. **Add business logic** - Services layer
5. **Connect HTTP layer** - API endpoints
6. **Test thoroughly** - Unit og integration tests
7. **Update documentation** - API docs og architecture notes

## 🚨 Common Anti-Patterns to Avoid

❌ **Don't put business logic in API endpoints**
❌ **Don't put HTTP concerns in CRUD functions**  
❌ **Don't skip authentication checks**
❌ **Don't return SQLAlchemy models directly from endpoints**
❌ **Don't hardcode configuration values**
❌ **Don't ignore error handling**
❌ **Don't forget to validate user ownership of resources**

✅ **Do follow the layered architecture**
✅ **Do use dependency injection**
✅ **Do validate all input data**
✅ **Do handle errors gracefully**
✅ **Do write comprehensive tests**
✅ **Do document your code**