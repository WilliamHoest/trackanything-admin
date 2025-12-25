from typing import Dict, Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

class HeuristicAnalyzer:
    """
    Handles heuristic-based analysis and fallback methods.
    """

    async def find_article_url_from_html(self, html: str, domain: str) -> Optional[str]:
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

    async def fallback_heuristic_analysis(self, article_html: str, article_url: str) -> Dict[str, Optional[str]]:
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
