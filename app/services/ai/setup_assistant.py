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

KRITISK — phrase-matching er bogstavelig:
Søgeord matches som eksakte fraser med ordgrænser. Et 4-ords søgeord matcher KUN hvis præcis de 4 ord optræder sammenhængende i teksten. Lange fraser er skrøbelige. Korte 1-2 ords søgeord er robuste og er det der i praksis sikrer 2-match-kravet.

Konsekvenser for dine søgeord — følg disse regler:
1. INKLUDER mindst 2 korte ankerord (1-2 ord) i HVERT emne der med stor sandsynlighed optræder verbatim i relevante artikler:
   - Hvis overvågningsemnet har ét kort, distinkt kernebegreb (fx et firmanavn, et personnavn, et stedsnavn): brug det som anker i alle emner.
   - Hvis overvågningsemnet er en begivenhed, konflikt eller abstrakt fænomen med et langt navn: identificer de 2-3 korte kerneord der faktisk optræder i avisoverskrifter om emnet, og inkluder dem i alle emner. Det lange navn egner sig til søgning men duer ikke som phrase-anker da det sjældent optræder verbatim.
2. HOLD de emne-specifikke søgeord distinkte: undgå at de samme specifikke søgeord optræder i flere emner — det giver forkert kategorisering via winner-takes-all.
3. UNDGÅ brede generiske enkeltord der ikke kvalificerer en artikel alene: "udgifter", "investeringer", "konkurrence", "forebyggelse", "overskud", "sundhed", "økonomi", "marked", "vækst". Kombinér dem med et ankerord i en frase, fx "[kernebegreb] økonomi" eller "[brand] aktie".
4. BLAND korte og lange søgeord i hvert emne: de korte (1-2 ord) sikrer 2-match-kravet, de lange (2-3 ord) sørger for præcis kategorisering via winner-takes-all.
5. INKLUDER faglige varianter inden for samme emne: produktnavne, aktive stoffer, personnavne, relevante myndigheder og institutioner. Brug danske navne og udtryk da kilderne er dansk presse.
6. UNDGÅ børstickers og akronymer der sjældent optræder i dansk presse. Brug i stedet fulde navne eller beskrivende fraser.

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
