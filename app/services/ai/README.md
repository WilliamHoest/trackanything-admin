# AI Service - Modular Architecture

Velstruktureret og modulær AI service til Atlas Intelligence Assistant med PydanticAI.

## 📁 Struktur

```
app/services/ai/
├── __init__.py              # Main exports (stream_chat_response, UserContext)
├── context.py               # UserContext Pydantic model
├── personas.py              # 5 AI personas + system prompt builder
├── agent.py                 # PydanticAI agent creation & management
└── tools/
    ├── __init__.py          # Tool exports
    ├── web_search.py        # Tavily web search tool
    ├── content_fetch.py     # Tavily content extraction tool
    └── mention_analysis.py  # Mentions analysis tool
```

## 🔧 Komponenter

### Context Model ([context.py](context.py))
- **UserContext**: Pydantic model til type-safe dependency injection
- Indeholder: user_id, user_profile, brands, mentions

### Personas ([personas.py](personas.py))
- **5 forskellige AI personas**:
  - `general` - Generel assistent (default)
  - `pr_expert` - PR og kommunikation
  - `policy_expert` - Politik og regulering
  - `market_research` - Markedsanalyse
  - `crisis_management` - Krisehåndtering
- `build_context_message()` - Bygger system prompt med persona + user context

### Agent Management ([agent.py](agent.py))
- **Agent caching**: Én agent per persona (performance)
- **DeepSeek model**: Via PydanticAI's native support
- **Tool registration**: Alle 3 tools registreres automatisk
- Temperature: 0.7, Max tokens: 800

### Tools ([tools/](tools/))

#### 1. Web Search ([web_search.py](tools/web_search.py))
- **Funktion**: `web_search(query: str)`
- **Bruger**: Tavily API
- **Formål**: Søg web for aktuel information
- **Returns**: Formateret resultat med titel, URL, content

#### 2. Content Fetch ([content_fetch.py](tools/content_fetch.py))
- **Funktion**: `fetch_page_content(url: str)`
- **Bruger**: Tavily API extract
- **Formål**: Hent indhold fra specifik URL
- **Returns**: Raw content (max 3000 chars)

#### 3. Mention Analysis ([mention_analysis.py](tools/mention_analysis.py))
- **Funktion**: `analyze_mentions(mentions: List[Dict])`
- **Bruger**: Ingen eksterne API'er
- **Formål**: Detaljeret analyse af mentions
- **Returns**: Formateret breakdown per brand/topic/platform

## 📦 Import Pattern

```python
from app.services.ai import UserContext, stream_chat_response

# Build context with UserContext model
context = UserContext(
    user_id="123",
    user_profile={...},
    brands=[...],
    recent_mentions=[...],
    recent_mentions_count=10
)

# Stream chat response with persona
async for chunk in stream_chat_response(
    message=user_message,
    conversation_history=history,
    context=context,
    persona="general"  # or pr_expert, policy_expert, market_research, crisis_management
):
    yield chunk
```

## 🔑 Key Features

### ✅ Async/Await Ready
- Alle tools bruger `asyncio.to_thread()` for Tavily sync calls
- Ingen blocking operations i event loop

### ✅ Error Handling
- Graceful degradation hvis Tavily API key mangler
- Detaljeret logging på alle levels
- Try/except i alle tool functions

### ✅ Performance
- Agent caching (én per persona)
- Tavily client singleton pattern
- Lazy initialization af resources

### ✅ Type Safety
- Pydantic validation af UserContext
- Type hints overalt
- IDE auto-completion support

## 🧪 Testing Tools Isolated

Du kan teste tools direkte:

```python
from app.services.ai.tools import web_search, fetch_page_content, analyze_mentions

# Test web search
result = await web_search("latest Tesla news")

# Test content fetch
content = await fetch_page_content("https://example.com/article")

# Test mention analysis
analysis = await analyze_mentions(mentions_list)
```

## 🔧 Configuration

Environment variables (via [app/core/config.py](../../core/config.py)):
```env
DEEPSEEK_API_KEY=sk-...        # Required for AI
TAVILY_API_KEY=tvly-...         # Required for web tools
```

## 📝 Adding New Tools

1. Create tool file: `app/services/ai/tools/my_tool.py`
2. Implement async function:
   ```python
   async def my_tool(param: str) -> str:
       # Tool logic here
       return result
   ```
3. Export in `tools/__init__.py`:
   ```python
   from .my_tool import my_tool
   __all__ = [..., 'my_tool']
   ```
4. Register in `agent.py`:
   ```python
   @agent.tool
   async def my_tool_wrapper(ctx: RunContext[UserContext], param: str) -> str:
       return await my_tool(param)
   ```

## 🏗️ Architecture Benefits

- **Separation of Concerns**: Hver komponent har ét ansvar
- **Testability**: Tools kan testes isoleret
- **Maintainability**: Let at finde og ændre kode
- **Scalability**: Nem at tilføje nye tools/personas
- **Type Safety**: Pydantic validation fanger fejl tidligt
