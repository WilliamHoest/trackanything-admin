import httpx
from urllib.parse import urlparse
from typing import Dict, Optional, List

from app.schemas.source_config import (
    SourceConfigCreate,
    SourceConfigAnalysisResponse
)
from app.crud.supabase_crud import SupabaseCRUD
from app.services.source_configuration.analyzers.ai_analyzer import AIAnalyzer
from app.services.source_configuration.analyzers.heuristic_analyzer import HeuristicAnalyzer

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
        self.ai_analyzer = AIAnalyzer()
        self.heuristic_analyzer = HeuristicAnalyzer()

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
            analysis_result = await self.ai_analyzer.analyze_source_structure(
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
            article_url = await self.heuristic_analyzer.find_article_url_from_html(homepage_html, domain)

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
