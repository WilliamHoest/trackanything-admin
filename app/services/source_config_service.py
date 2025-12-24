"""
Source Configuration Service

Handles AI-assisted analysis of URLs to extract CSS selectors for scraping.
This service is responsible for:
- Fetching raw HTML from URLs
- Analyzing HTML structure to suggest selectors
- Saving/updating source configurations in the database

Separation of Concerns:
- This service handles CONFIGURATION (analysis & storage)
- ScrapingService handles EXECUTION (actual scraping using configs)
"""

import httpx
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from typing import Dict, Optional, List
from datetime import datetime
from openai import AsyncOpenAI

from app.schemas.source_config import (
    SourceConfigCreate,
    SourceConfigAnalysisResponse
)
from app.crud.supabase_crud import SupabaseCRUD
from app.core.config import settings
from app.core.selectors import GENERIC_SELECTORS_MAP


# === Configuration ===
TIMEOUT_SECONDS = 15
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class SourceConfigService:
    """
    Service for analyzing URLs and managing source configurations.

    This service is focused on the "Admin" workflow:
    1. Admin provides a URL
    2. Service fetches and analyzes the HTML
    3. AI/heuristics suggest CSS selectors
    4. Configuration is saved to database
    """

    def __init__(self, crud: SupabaseCRUD):
        self.crud = crud

    async def analyze_url(self, url: str) -> SourceConfigAnalysisResponse:
        """
        Analyze a URL to extract CSS selectors and search patterns.

        Workflow:
        1. Fetch raw HTML from the article URL
        2. Extract root domain and fetch homepage HTML
        3. Use AI to analyze both article and homepage
        4. Suggest selectors (title, content, date) + search URL pattern
        5. Save configuration to database
        6. Return suggested configuration

        Args:
            url: The article URL to analyze

        Returns:
            SourceConfigAnalysisResponse with suggested selectors and search pattern
        """
        # Extract domain from URL
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove www. prefix for consistency
        if domain.startswith('www.'):
            domain = domain[4:]

        # Construct root domain URL
        root_url = f"{parsed.scheme}://{parsed.netloc}"

        try:
            # Step 1: Fetch article HTML
            article_html = await self._fetch_html(url)

            # Step 2: Fetch homepage HTML for search pattern detection
            homepage_html = await self._fetch_html(root_url)

            # Step 3: Analyze structure (Standard Selectors + AI Verification)
            analysis_result = await self._analyze_source_structure(
                article_html=article_html,
                homepage_html=homepage_html,
                article_url=url,
                root_url=root_url
            )

            # Step 4: Save to database
            config_data = SourceConfigCreate(
                domain=domain,
                title_selector=analysis_result.get('title_selector'),
                content_selector=analysis_result.get('content_selector'),
                date_selector=analysis_result.get('date_selector'),
                search_url_pattern=analysis_result.get('search_url_pattern')
            )

            saved_config = await self.crud.create_or_update_source_config(config_data)

            if saved_config:
                return SourceConfigAnalysisResponse(
                    domain=domain,
                    title_selector=analysis_result.get('title_selector'),
                    content_selector=analysis_result.get('content_selector'),
                    date_selector=analysis_result.get('date_selector'),
                    search_url_pattern=analysis_result.get('search_url_pattern'),
                    confidence=analysis_result.get('confidence', 'medium'),
                    message=f"Configuration saved for {domain}"
                )
            else:
                return SourceConfigAnalysisResponse(
                    domain=domain,
                    title_selector=analysis_result.get('title_selector'),
                    content_selector=analysis_result.get('content_selector'),
                    date_selector=analysis_result.get('date_selector'),
                    search_url_pattern=analysis_result.get('search_url_pattern'),
                    confidence=analysis_result.get('confidence', 'low'),
                    message=f"Failed to save configuration for {domain}"
                )

        except Exception as e:
            print(f"❌ Error analyzing URL {url}: {e}")
            return SourceConfigAnalysisResponse(
                domain=domain,
                confidence="low",
                message=f"Analysis failed: {str(e)}"
            )

    async def refresh_config_from_homepage(self, domain: str) -> SourceConfigAnalysisResponse:
        """
        Refresh source configuration by analyzing the homepage.

        Workflow:
        1. Fetch homepage HTML from https://{domain}
        2. Find ONE valid article URL using heuristics
        3. Call analyze_url() with that article
        4. Return updated config + verification URL

        Args:
            domain: Domain to refresh (e.g., 'berlingske.dk')

        Returns:
            SourceConfigAnalysisResponse with updated selectors
        """
        # Normalize domain
        domain = domain.lower()
        if domain.startswith('www.'):
            domain = domain[4:]

        homepage_url = f"https://{domain}"

        try:
            print(f"🔄 Refreshing config for {domain}...")
            homepage_html = await self._fetch_html(homepage_url)

            # Find article URL from homepage
            article_url = await self._find_article_url_from_html(homepage_html, domain)

            if not article_url:
                return SourceConfigAnalysisResponse(
                    domain=domain,
                    confidence="low",
                    message=f"No article URL found on homepage of {domain}"
                )

            print(f"   ✅ Found article: {article_url}")

            # Re-analyze with found article
            result = await self.analyze_url(article_url)
            result.message = f"{result.message} (verified with: {article_url})"

            return result

        except Exception as e:
            return SourceConfigAnalysisResponse(
                domain=domain,
                confidence="low",
                message=f"Refresh failed: {str(e)}"
            )

    async def _find_article_url_from_html(self, html: str, domain: str) -> Optional[str]:
        """
        Find ONE valid article URL from HTML using strict validation.

        Strategy:
        - Iterate through all links
        - Validate each link against blacklist, domain, and path length
        - Return first valid article URL

        Args:
            html: Raw HTML content
            domain: Expected domain

        Returns:
            Full article URL or None if not found
        """
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Helper for strict validation
            def is_valid_article_url(url: str, target_domain: str) -> bool:
                # Substrings that invalidate a URL
                # We use /slashes/ for short words to avoid matching substrings in valid words
                # e.g. "tag" matches "fredag", so we use "/tag/"
                BLACKLIST_KEYWORDS = [
                    "e-avis", "login", "log-ind", "shop", 
                    "abonnement", "kundeservice", "auth", ".pdf",
                    "tilbud", "annonce", "/profile/", "/user/",
                    "minside", "arkiv", "nyhedsbreve", "/podcast/", 
                    "/video/", "galleri", "/play/",
                    "/tag/", "/kategori/", "/emne/", "/tema/", "/sektion/"
                ]
                
                try:
                    parsed = urlparse(url)
                    path = parsed.path
                    url_lower = url.lower()

                    # 1. Check Blacklist
                    if any(keyword in url_lower for keyword in BLACKLIST_KEYWORDS):
                        return False

                    # 2. Check Domain (allow subdomains unless it's e-avis which is caught above)
                    clean_target = target_domain.replace("www.", "")
                    if clean_target not in parsed.netloc:
                        return False

                    # 3. Check Path Length (Articles usually have long slugs)
                    if len(path) < 30:
                        return False
                        
                    return True
                except Exception:
                    return False

            # Iterate through all links
            for link in soup.select("a[href]"):
                href = link.get("href", "")
                if not href:
                    continue

                full_url = urljoin(f"https://{domain}", href)
                
                if is_valid_article_url(full_url, domain):
                    return full_url

            return None

        except Exception as e:
            print(f"   ⚠️ Error finding article URL: {e}")
            return None

    async def _fetch_html(self, url: str) -> str:
        """
        Fetch raw HTML content from a URL.

        Args:
            url: The URL to fetch

        Returns:
            Raw HTML content as string

        Raises:
            httpx.HTTPError: If the request fails
        """
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            headers = {"User-Agent": USER_AGENT}
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return response.text

    async def _verify_content_quality(self, text: str, type: str) -> bool:
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

    async def _analyze_source_structure(
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
Look for <form action="..."> or <input name="q">.
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
                        is_valid = await self._verify_content_quality(text, key)

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


    async def _fallback_heuristic_analysis(self, article_html: str, article_url: str) -> Dict[str, Optional[str]]:
        """
        Fallback method using heuristic analysis when AI fails.

        Note: This fallback cannot detect search_url_pattern, so it returns None.

        Args:
            article_html: Raw HTML content from article page
            article_url: Original article URL

        Returns:
            Dictionary with suggested selectors and confidence
        """
        print(f"🔄 Falling back to heuristic analysis for {article_url}")

        soup = BeautifulSoup(article_html, 'lxml')

        # Heuristic 1: Look for common article title patterns
        title_selector = None
        title_candidates = [
            'article h1',
            'h1[itemprop="headline"]',
            'h1.article-title',
            '.post-title h1',
            'header h1',
            'main h1'
        ]
        for selector in title_candidates:
            if soup.select_one(selector):
                title_selector = selector
                break

        # Heuristic 2: Look for common content patterns
        content_selector = None
        content_candidates = [
            '[itemprop="articleBody"]',
            'article .article-content',
            'article .post-content',
            '.article-body',
            'main article',
            'article'
        ]
        for selector in content_candidates:
            if soup.select_one(selector):
                content_selector = selector
                break

        # Heuristic 3: Look for common date patterns
        date_selector = None
        date_candidates = [
            'time[datetime]',
            '[itemprop="datePublished"]',
            'time.published',
            '.publish-date',
            '.article-date',
            'article time'
        ]
        for selector in date_candidates:
            if soup.select_one(selector):
                date_selector = selector
                break

        # Determine confidence
        found_count = sum([bool(title_selector), bool(content_selector), bool(date_selector)])
        if found_count == 3:
            confidence = "medium"  # Lower confidence for heuristics
        elif found_count >= 1:
            confidence = "low"
        else:
            confidence = "low"

        print(f"   Title: {title_selector}")
        print(f"   Content: {content_selector}")
        print(f"   Date: {date_selector}")
        print(f"   Search Pattern: None (heuristic cannot detect)")
        print(f"   Confidence: {confidence}")

        return {
            'title_selector': title_selector,
            'content_selector': content_selector,
            'date_selector': date_selector,
            'search_url_pattern': None,  # Cannot be determined heuristically
            'confidence': confidence
        }

    async def get_config_for_domain(self, domain: str) -> Optional[Dict]:
        """
        Get the saved configuration for a specific domain.

        Args:
            domain: The domain to look up (e.g., 'berlingske.dk')

        Returns:
            Dictionary with configuration or None if not found
        """
        # Normalize domain (remove www.)
        domain = domain.lower()
        if domain.startswith('www.'):
            domain = domain[4:]

        return await self.crud.get_source_config_by_domain(domain)

    async def list_all_configs(self) -> List[Dict]:
        """
        List all saved source configurations.

        Returns:
            List of all source configurations
        """
        return await self.crud.get_all_source_configs()

    async def delete_config(self, domain: str) -> bool:
        """
        Delete a source configuration by domain.

        Args:
            domain: The domain to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        # Normalize domain
        domain = domain.lower()
        if domain.startswith('www.'):
            domain = domain[4:]

        return await self.crud.delete_source_config_by_domain(domain)
