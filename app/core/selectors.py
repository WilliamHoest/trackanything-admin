"""
Shared Generic CSS Selectors for Web Scraping.

These lists are used as a "best guess" fallback when:
1. No specific source configuration exists for a domain.
2. A specific configured selector fails to find content.
3. AI analysis fails to suggest a valid selector.
"""

GENERIC_TITLE_SELECTORS = [
    # --- Social Media Specifics (High Priority: Clean Content) ---
    'h1[slot="title"]',                    # Reddit Modern (Precise title)
    'h1[data-testid="post-title"]',        # Reddit Alternative
    'h1[role="heading"]',                  # Twitter/X Post Title
    'div[data-testid="tweetText"] h2',     # Twitter/X Thread Title
    'h1.userContent',                      # Facebook Post Title (if exists)

    # --- Standard News & Blogs ---
    'h1[itemprop="headline"]',
    'h1.article-title',
    'article h1',
    'h1.entry-title',  # WordPress standard
    'h1.post-title',
    'h1.headline',
    'header h1',
    '.post-title h1',
    'main h1',
    'h1',

    # --- Broad Fallbacks (Use only if everything else fails) ---
    'shreddit-title',                      # Reddit Container (may contain extra elements)
    '[data-testid="tweetText"]',           # Twitter/X fallback (uses text as title if none found)
    'title'                                 # Last resort: page title
]

GENERIC_CONTENT_SELECTORS = [
    # --- Social Media Specifics (Priority: Clean text only, no noise) ---
    'div[slot="text-body"]',                  # Reddit Modern (ONLY text, no noise)
    'div[data-click-id="text"]',              # Reddit Alternative
    'div[class*="md"] p',                     # Reddit markdown content paragraphs
    'div[data-testid="tweetText"]',           # Twitter/X Clean Text
    'div[data-testid="card.layoutLarge.detail"] p',  # Twitter/X Cards
    'div[data-ad-preview="message"]',         # Facebook Public Posts
    'div.userContent',                        # Facebook User-Generated Content
    '.feed-shared-update-v2__description',    # LinkedIn Posts
    'article[data-testid="tweet"]',           # Twitter/X Full Tweet (if needed)

    # --- Standard Semantic Web ---
    'div[itemprop="articleBody"]',
    'div.article-body',
    'div.post-content',
    'div.entry-content',
    '[itemprop="articleBody"]',
    'article .article-content',
    '.article-body',
    'section[itemprop="articleBody"]',

    # --- CMS Variations ---
    'div[class*="article-body"]',             # Catch variations like js-article-body
    'div[class*="rich-text"]',                # Common in CMSs
    'div[class*="post-body"]',
    'div[class*="entry-content"]',            # WordPress variations

    # --- Broad Fallbacks (Use only if everything else fails) ---
    'shreddit-post',                          # Reddit Container (WARNING: May contain noise, low priority)
    '[role="article"]',
    'main article',
    'article',
    'main'                                     # Ultimate fallback
]

GENERIC_DATE_SELECTORS = [
    # --- Social Media Specifics ---
    'faceplate-timeago',                         # Reddit Modern
    'time[data-testid="timestamp"]',             # Generic SPAs (Twitter/X)
    'time[data-testid="tweet-timestamp"]',       # Twitter/X Specific
    'a[href*="/status/"] time',                  # Twitter/X context link
    'abbr[data-utime]',                          # Facebook Unix timestamp
    'abbr[title][data-shorten]',                 # Facebook formatted time
    'time.live-timestamp',                       # LinkedIn

    # --- Standard Semantic Web (High Priority) ---
    'meta[property="article:published_time"]',   # Meta tag priority (OpenGraph)
    'meta[name="publish-date"]',                 # Meta tag alternative
    'time[datetime]',
    '[itemprop="datePublished"]',
    'time.published',

    # --- CSS Class Variations ---
    '.publish-date',
    '.article-date',
    '.date',
    '.timestamp',
    'article time',
    '.published-date',
    'span[class*="date"]',
    'span[class*="time"]'
]

GENERIC_SELECTORS_MAP = {
    'title_selector': GENERIC_TITLE_SELECTORS,
    'content_selector': GENERIC_CONTENT_SELECTORS,
    'date_selector': GENERIC_DATE_SELECTORS
}