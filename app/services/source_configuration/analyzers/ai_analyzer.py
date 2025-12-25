import json
import re
from typing import Dict, Optional
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
from app.core.config import settings
from app.core.selectors import GENERIC_SELECTORS_MAP

class AIAnalyzer:
    """
    Handles AI-powered analysis of HTML content to find selectors and verify quality.
    """

    async def verify_content_quality(self, text: str, type: str) -> bool:
        """
        Verify extracted text using AI (Judge).
        
        Args:
            text: The extracted text content
            type: 'title_selector' or 'content_selector'
        """
        if not text:
            return False

        # --- 1. Basic Heuristics (Fail Fast) ---
        clean_text = text.strip()
        
        if type == 'title_selector':
            if len(clean_text) < 10: # Titles are rarely super short
                print(f"      ⚠️ Rejected: Title too short (<10 chars)")
                return False
                
        elif type == 'content_selector':
            if len(clean_text) < 50: # Content must be substantial
                print(f"      ⚠️ Rejected: Content too short (<50 chars)")
                return False
        
        # --- 2. AI Verification ---
        try:
            client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url="https://api.deepseek.com"
            )
            
            if type == 'title_selector':
                system_prompt = """You are a Quality Assurance bot for a News Scraper.
Is this text a valid NEWS ARTICLE HEADLINE?
YES: "Global markets rally as inflation drops", "Regeringen varsler nye reformer"
NO: "Menu", "Seneste nyt", "Mest læste", "Forside", "Log ind", "Abonnement"
Return ONLY JSON: {"is_valid": true/false}"""
            
            else: # content_selector
                system_prompt = """You are a Quality Assurance bot for a News Scraper.
Is this text valid ARTICLE CONTENT (body text, lead paragraph, or paywall teaser)?
YES: Narrative text, sentences, paragraphs. "Statsministeren udtalte i går..."
YES (Paywall): "Det var en mørk aften... [Log ind for at læse mere]"
NO: Lists of links ("Læs også: ..."), Navigation menus, Cookie banners, Footer text, Metadata only.
Return ONLY JSON: {"is_valid": true/false}"""

            user_prompt = f"Analyze:\n{clean_text[:500]}"

            response = await client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=50
            )
            
            content = response.choices[0].message.content.strip().replace('```json', '').replace('```', '')
            result = json.loads(content)
            
            if not result.get('is_valid'):
                print(f"      ⚠️ AI Rejected: Looks like noise/list")
                return False
                
            return True

        except Exception as e:
            print(f"      ⚠️ Verification failed (failing open): {e}")
            return True

    async def analyze_source_structure(
        self,
        article_html: str,
        homepage_html: str,
        article_url: str,
        root_url: str
    ) -> Dict[str, Optional[str]]:
        """
        Analyze source structure using Standard Selectors + AI Verification.
        """
        validated_selectors = {}
        soup = BeautifulSoup(article_html, 'lxml')
        validation_count = 0

        # === Step 1: Detect Search Pattern (Homepage Analysis via AI) ===
        try:
            print(f"   🤖 Detecting search pattern on homepage via AI...")
            client = AsyncOpenAI(api_key=settings.deepseek_api_key, base_url="https://api.deepseek.com")
            
            search_prompt = """Analyze this Homepage HTML and find the SEARCH URL pattern.
Look for <form action=\"...\"> or <input name=\"q\">
Return ONLY JSON: {"search_url_pattern": "https://domain.com/search?q={keyword}"} OR null."""
            
            response = await client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": search_prompt},
                    {"role": "user", "content": homepage_html[:8000]}
                ],
                temperature=0.1, max_tokens=100
            )
            
            content = response.choices[0].message.content.strip().replace('```json', '').replace('```', '')
            search_res = json.loads(content)
            pattern = search_res.get('search_url_pattern')
            
            if pattern and '{keyword}' in pattern:
                validated_selectors['search_url_pattern'] = pattern
                print(f"   ✅ search_url_pattern: {pattern}")
                validation_count += 1
            else:
                validated_selectors['search_url_pattern'] = None
                print(f"   ⚠️ search_url_pattern: Not detected")
                
        except Exception as e:
            print(f"   ❌ Search pattern detection failed: {e}")
            validated_selectors['search_url_pattern'] = None


        # === Step 2: Detect Selectors (Iterate Generics + AI Verification) ===
        
        for key in ['title_selector', 'content_selector', 'date_selector']:
            validated_selectors[key] = None
            print(f"   🔍 Testing candidates for {key}...")
            
            candidates = GENERIC_SELECTORS_MAP.get(key, [])
            
            for selector in candidates:
                try:
                    element = soup.select_one(selector)
                    if not element:
                        continue
                        
                    # Extract Text
                    if element.name == 'meta':
                        text = element.get('content', '')
                    elif key == 'date_selector' and element.has_attr('datetime'):
                        text = element.get('datetime')
                    else:
                        text = element.get_text(strip=True)
                    
                    if not text:
                        continue

                    # === VERIFICATION ===
                    is_valid = False
                    
                    # DATE: Use Heuristic
                    if key == 'date_selector':
                        if re.search(r'202[0-9]', text):
                            is_valid = True
                        else:
                            print(f"      ⚠️ Rejected Date: '{text}' (no year found)")
                    
                    # TITLE & CONTENT: Use AI Judge
                    else:
                        is_valid = await self.verify_content_quality(text, key)

                    if is_valid:
                        validated_selectors[key] = selector
                        validation_count += 1
                        print(f"   ✅ Verified: {selector}")
                        preview = text[:1000].replace('\n', ' ')
                        print(f"      👀 Preview: \"{preview}...\"")
                        break # Stop at first valid selector
                
                except Exception as e:
                    continue
            
            if not validated_selectors[key]:
                print(f"   ❌ No valid {key} found in generic list.")


        # Determine confidence
        if validation_count >= 3:
            confidence = "high"
        elif validation_count >= 2:
            confidence = "medium"
        else:
            confidence = "low"

        validated_selectors['confidence'] = confidence
        print(f"🎯 Analysis complete. Confidence: {confidence}")
        
        return validated_selectors
