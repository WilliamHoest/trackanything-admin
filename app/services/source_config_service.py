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
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Dict, Optional, List
from datetime import datetime
from openai import AsyncOpenAI

from app.schemas.source_config import (
    SourceConfigCreate,
    SourceConfigAnalysisResponse
)
from app.crud.supabase_crud import SupabaseCRUD
from app.core.config import settings


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

            # Step 3: Analyze both HTMLs with AI
            analysis_result = await self._suggest_selectors_with_llm(
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

    async def _suggest_selectors_with_llm(
        self,
        article_html: str,
        homepage_html: str,
        article_url: str,
        root_url: str
    ) -> Dict[str, Optional[str]]:
        """
        Analyze article and homepage HTML using DeepSeek AI.

        This method uses DeepSeek's LLM to:
        1. Suggest CSS selectors for article content (from article HTML)
        2. Detect search URL pattern (from homepage HTML)

        Args:
            article_html: Raw HTML from the article page
            homepage_html: Raw HTML from the homepage
            article_url: The article URL (for context)
            root_url: The root domain URL (for context)

        Returns:
            Dictionary with suggested selectors, search pattern, and confidence level
        """
        try:
            # Initialize DeepSeek client (OpenAI-compatible API)
            client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url="https://api.deepseek.com"
            )

            # Truncate HTMLs to avoid token limits
            # Article HTML: Keep beginning and middle (~10k chars)
            article_length = len(article_html)
            if article_length > 10000:
                article_snippet = article_html[:5000] + "\n\n... [article truncated] ...\n\n" + article_html[article_length//2:article_length//2 + 5000]
            else:
                article_snippet = article_html

            # Homepage HTML: Keep beginning only (~5k chars) - we mainly need the header/nav
            homepage_snippet = homepage_html[:5000]

            # Prepare the prompt
            system_prompt = """You are an expert web scraper and HTML analyst. Your task is to:
1. Identify CSS selectors for extracting content from news articles
2. Detect the search URL pattern from the homepage

Return ONLY a valid JSON object with these keys:
- title_selector: CSS selector for the article title
- content_selector: CSS selector for the article body/content
- date_selector: CSS selector for the publication date
- search_url_pattern: The search URL with {keyword} as placeholder

Guidelines for CSS Selectors:
1. Prefer specific selectors (e.g., "article h1.title") over generic ones
2. Use semantic HTML tags when available (article, time, etc.)
3. Look for Schema.org attributes (itemprop="headline", etc.)
4. Avoid overly specific selectors that might break easily
5. Return null if you cannot find a reliable selector

Guidelines for Search Pattern:
1. Look for <form> tags with action attributes containing "search", "søg", "find"
2. Look for <input> tags with type="search" or name="q", "query", "søg"
3. Construct a URL pattern like: https://domain.com/search?q={keyword}
4. If no search form is found, look for RSS feed links and return those
5. Return null if no search mechanism is found

Do NOT include markdown formatting or explanations. Return ONLY the JSON object."""

            user_prompt = f"""Analyze these HTMLs and suggest configuration:

ARTICLE PAGE ({article_url}):
{article_snippet}

HOMEPAGE ({root_url}):
{homepage_snippet}

Extract:
1. CSS selectors from the ARTICLE PAGE
2. Search URL pattern from the HOMEPAGE"""

            print(f"🤖 Calling DeepSeek AI to analyze {article_url}...")

            # Call DeepSeek API
            response = await client.chat.completions.create(
                model="deepseek-chat",  # DeepSeek's main model
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent output
                max_tokens=500
            )

            # Extract and parse response
            ai_response = response.choices[0].message.content.strip()
            print(f"📝 DeepSeek response: {ai_response[:200]}...")

            # Remove markdown code blocks if present
            if ai_response.startswith("```"):
                ai_response = ai_response.strip("`").strip()
                if ai_response.startswith("json"):
                    ai_response = ai_response[4:].strip()

            # Parse JSON
            selectors = json.loads(ai_response)

            # Validate selectors by testing them against the article HTML
            soup = BeautifulSoup(article_html, 'lxml')
            validated_selectors = {}
            validation_count = 0

            for key in ['title_selector', 'content_selector', 'date_selector']:
                selector = selectors.get(key)
                if selector:
                    try:
                        # Test if selector works
                        element = soup.select_one(selector)
                        if element:
                            validated_selectors[key] = selector
                            validation_count += 1
                            print(f"   ✅ {key}: {selector}")
                        else:
                            validated_selectors[key] = None
                            print(f"   ❌ {key}: {selector} (not found in HTML)")
                    except Exception as e:
                        validated_selectors[key] = None
                        print(f"   ❌ {key}: {selector} (invalid selector: {e})")
                else:
                    validated_selectors[key] = None

            # Validate search URL pattern
            search_pattern = selectors.get('search_url_pattern')
            if search_pattern:
                # Basic validation: should contain {keyword} placeholder
                if '{keyword}' in search_pattern:
                    validated_selectors['search_url_pattern'] = search_pattern
                    print(f"   ✅ search_url_pattern: {search_pattern}")
                else:
                    validated_selectors['search_url_pattern'] = None
                    print(f"   ❌ search_url_pattern: {search_pattern} (missing {{keyword}} placeholder)")
            else:
                validated_selectors['search_url_pattern'] = None
                print(f"   ⚠️ search_url_pattern: Not detected")

            # Determine confidence based on validation
            if validation_count == 3:
                confidence = "high"
            elif validation_count >= 2:
                confidence = "medium"
            elif validation_count >= 1:
                confidence = "low"
            else:
                confidence = "low"

            validated_selectors['confidence'] = confidence

            print(f"🎯 Analysis complete. Confidence: {confidence}")
            return validated_selectors

        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse DeepSeek response as JSON: {e}")
            # Fallback to heuristic analysis
            return await self._fallback_heuristic_analysis(article_html, article_url)

        except Exception as e:
            print(f"❌ DeepSeek API error: {e}")
            # Fallback to heuristic analysis
            return await self._fallback_heuristic_analysis(article_html, article_url)

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
