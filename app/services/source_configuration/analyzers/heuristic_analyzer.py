import re
from typing import Dict, List, Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

_DATE_PATH_RE = re.compile(r"/20\d{2}/\d{2}/\d{2}/")
_ARTICLE_ID_RE = re.compile(r"(?:article|art)\d{5,}|/\d{6,}(?:[./-]|$)", re.IGNORECASE)
_LONG_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){3,}$", re.IGNORECASE)

_BLACKLIST = [
    # Navigation / institutional
    "kontakt", "contact", "about", "om-os", "/om_", "redaktion",
    "presse", "jobs", "karriere", "annoncør", "advertise",
    # Auth / account
    "login", "log-ind", "log-ud", "signup", "register",
    "/profile/", "/user/", "minside", "mit-", "min-side",
    # Commerce
    "e-avis", "shop", "abonnement", "kundeservice", "tilbud",
    # Non-content
    "nyhedsbreve", "newsletter", "arkiv", "annonce",
    "/podcast/", "/video/", "galleri", "/play/", ".pdf",
    "/tag/", "/kategori/", "/emne/", "/tema/", "/sektion/",
    "cookiepolitik", "privatlivspolitik", "auth",
]


class HeuristicAnalyzer:
    """
    Handles heuristic-based analysis and fallback methods.
    """

    async def find_article_url_from_html(self, html: str, domain: str) -> Optional[str]:
        """
        Find ONE valid article URL from HTML using strict validation + scoring.

        Strategy:
        - Filter links against an expanded blacklist and domain/length checks
        - Score candidates: date-path > article-ID > long-slug > generic long path
        - Return highest-scoring candidate

        Args:
            html: Raw HTML content
            domain: Expected domain

        Returns:
            Full article URL or None if not found
        """
        try:
            soup = BeautifulSoup(html, 'lxml')
            clean_target = domain.replace("www.", "")

            def _score(url: str) -> int:
                parsed_u = urlparse(url)
                path = parsed_u.path
                # Prefer exact domain match over subdomains (e.g. tv2.dk > vejr.tv2.dk)
                score = 10 if parsed_u.netloc in (clean_target, f"www.{clean_target}") else 0
                if _DATE_PATH_RE.search(path):
                    score += 3
                elif _ARTICLE_ID_RE.search(path):
                    score += 2
                else:
                    segments = [s for s in path.strip("/").split("/") if s]
                    if any(_LONG_SLUG_RE.match(s) for s in segments):
                        score += 1
                return score

            def is_valid_article_url(url: str) -> bool:
                try:
                    parsed = urlparse(url)
                    url_lower = url.lower()
                    if any(kw in url_lower for kw in _BLACKLIST):
                        return False
                    if clean_target not in parsed.netloc:
                        return False
                    if len(parsed.path) < 30:
                        return False
                    return True
                except Exception:
                    return False

            candidates: List[tuple[int, str]] = []
            for link in soup.select("a[href]"):
                href = link.get("href", "")
                if not href:
                    continue
                full_url = urljoin(f"https://{domain}", href)
                if is_valid_article_url(full_url):
                    score = _score(full_url)
                    candidates.append((score, full_url))

            if not candidates:
                return None

            # Return highest-scoring candidate (stable sort keeps DOM order for ties)
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

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
