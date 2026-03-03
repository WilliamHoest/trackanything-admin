import json
from typing import List
from openai import AsyncOpenAI
from app.core.config import settings
from app.schemas.ai_setup import AISetupTopic


SYSTEM_PROMPT = """Du er ekspert i dansk medieovervågning. Baseret på brand-navn og beskrivelse, generer 3-5 relevante emner med 4-8 søgeord per emne.

TEKNISK KONTEKST — søgekilder:
Søgeordene sendes som query-strenge til fire datakilder: GNews API, SerpAPI (Google News), RSS-feeds (DR, TV2) og web-scraping af Politiken, Berlingske m.fl.

TEKNISK KONTEKST — matchinglogik:
Når artikler er scraped, matches søgeordene mod artiklernes overskrift og indhold via regex (phrase-matching med word boundaries, case-insensitive).
Scoringssystem:
- Score = antal distinkte søgeord der matcher (ét point per søgeord der findes i titel eller brødtekst)
- En artikel gemmes KUN hvis mindst 2 forskellige søgeord fra samme emne matcher
- Artiklen tildeles det emne med flest matchende søgeord (winner-takes-all)
- Ingen fallback: matcher en artikel færre end 2 søgeord, gemmes den slet ikke

Konsekvenser for dine søgeord — følg disse regler:
1. GRUPPER relaterede termer inden for samme emne: jo flere søgeord fra ét emne der optræder i én artikel, jo sikrere gemmes den
2. HOLD topics distinkte: undgå at samme søgeord optræder i flere topics — det giver forkert kategorisering
3. UNDGÅ brede enkeltord som "sundhed", "økonomi", "teknologi" alene — de matcher for sjældent sammen og artikler droppes
4. FORETRÆK fraser på 2-3 ord: de er mere præcise og matcher mere specifikt end enkeltord
5. INKLUDER varianter inden for samme emne: firmanavne på både dansk og engelsk, forkortelser, produktnavne (f.eks. "Novo Nordisk", "Novo", "NVO", "Ozempic" — alle i samme emne)

Returner KUN valid JSON uden markdown: {"topics": [{"name": "...", "keywords": ["..."]}]}"""


async def generate_setup(brand_name: str, description: str) -> List[AISetupTopic]:
    """Use DeepSeek to generate monitoring topics and keywords for a brand."""
    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key.get_secret_value(),
        base_url="https://api.deepseek.com"
    )

    user_prompt = f"Brand: {brand_name}\nBeskrivelse: {description}"

    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=1000,
    )

    content = response.choices[0].message.content.strip()
    # Strip markdown code fences if present
    content = content.replace("```json", "").replace("```", "").strip()

    data = json.loads(content)
    return [AISetupTopic(**topic) for topic in data["topics"]]
