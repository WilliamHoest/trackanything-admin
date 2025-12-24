"""
Shared Generic CSS Selectors for Web Scraping.

These lists are used as a "best guess" fallback when:
1. No specific source configuration exists for a domain.
2. A specific configured selector fails to find content.
3. AI analysis fails to suggest a valid selector.
"""

GENERIC_TITLE_SELECTORS = [
    'article h1',
    'h1[itemprop="headline"]',
    'h1.article-title',
    'h1.entry-title',  # Wordpress standard
    'h1.post-title',
    'h1.headline',
    'header h1',
    '.post-title h1',
    'main h1',
    'h1'
]

GENERIC_CONTENT_SELECTORS = [
    '[itemprop="articleBody"]',
    'article .article-content',
    '.article-body',
    '.entry-content',  # Wordpress standard
    '.post-content',
    'div[class*="article-body"]', # Catch variations like js-article-body
    'div[class*="rich-text"]',    # Common in CMSs
    'main article',
    'article',
    'main'  # Ultimate fallback
]

GENERIC_DATE_SELECTORS = [
    'time[datetime]',
    '[itemprop="datePublished"]',
    'meta[property="article:published_time"]', # Meta tag fallback
    'time.published',
    '.publish-date',
    '.article-date',
    '.date',
    '.timestamp',
    'article time'
]

GENERIC_SELECTORS_MAP = {
    'title_selector': GENERIC_TITLE_SELECTORS,
    'content_selector': GENERIC_CONTENT_SELECTORS,
    'date_selector': GENERIC_DATE_SELECTORS
}