"""
AI-based Relevance Filter for the scraping pipeline.

Uses DeepSeek API to evaluate if scraped articles are relevant
to their associated keywords/brand context before saving to database.
"""

import httpx
import logging
import asyncio
from typing import List, Dict, Tuple
from app.core.config import settings

logger = logging.getLogger("scraping.relevance_filter")


class RelevanceFilter:
    """
    Evaluates article relevance using DeepSeek V3 API.

    Features:
    - Parallel execution for high performance
    - Fail-open design: Defaults to True on API failure to prevent data loss
    - Cost-optimized prompting
    """

    API_URL = "https://api.deepseek.com/v1/chat/completions"
    TIMEOUT_SECONDS = 15.0  # Increased slightly for parallel batches

    def __init__(self):
        self.api_key = settings.deepseek_api_key
        self.model = settings.deepseek_model

    async def _check_single_relevance(self, client: httpx.AsyncClient, text: str, context: str, index: int) -> Tuple[int, bool]:
        """
        Helper method to check a single mention's relevance.
        Returns tuple (index, is_relevant) to maintain order after gather.
        """
        if not text or not context:
            return index, True

        # Truncate text to avoid token limits and reduce cost (keep first 600 chars - title + start of lead)
        truncated_text = text[:600] if len(text) > 600 else text

        prompt = (
            f"You are a strict media analyst. Is the following article PRIMARILY about these topics: '{context}'?\n\n"
            f"Article: '{truncated_text}'\n\n"
            f"Rules:\n"
            f"- YES only if the article's main subject directly concerns the topics above\n"
            f"- NO if the topics appear only in sidebars, related links, ads, or as brief passing references\n"
            f"- NO if the article is primarily about something unrelated (sports, accidents, weather, politics, etc.)\n"
            f"- When in doubt, reply NO\n\n"
            f"Reply ONLY with YES or NO."
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a strict relevance classifier. Reply ONLY with YES or NO. Only YES if the article's primary subject matches. Default to NO when uncertain."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 5,  # Only need YES or NO
            "temperature": 0.0  # Deterministic response
        }

        try:
            response = await client.post(
                self.API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            result = response.json()
            answer = result["choices"][0]["message"]["content"].strip().upper()
            
            # Check for YES (handling potential punctuation like "YES.")
            is_relevant = "YES" in answer

            return index, is_relevant

        except Exception as e:
            logger.error(f"Relevance check failed for item {index}: {e}. Defaulting to True (fail-open).")
            return index, True

    async def filter_mentions(
        self,
        mentions: List[Dict],
        keywords: List[str]
    ) -> List[Dict]:
        """
        Filter a list of mentions in PARALLEL, keeping only those relevant to the keywords.

        Args:
            mentions: List of mention dictionaries with 'title' and optionally 'content_teaser'
            keywords: List of keywords to check relevance against

        Returns:
            Filtered list containing only relevant mentions
        """
        if not mentions:
            return []

        if not keywords:
            logger.warning("No keywords provided for filtering, returning all mentions")
            return mentions

        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY not configured, skipping AI filter")
            return mentions

        # Prepare context
        # Limit context length to avoid huge prompts if many keywords exist
        context = ", ".join(keywords[:20]) # Take top 20 keywords max to keep prompt focused
        if len(keywords) > 20:
            context += "..."

        logger.info(f"🤖 Starting parallel AI relevance check for {len(mentions)} mentions...")

        # Create a single client for all requests (more efficient connection pooling)
        async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
            tasks = []
            for i, mention in enumerate(mentions):
                # Build text from title and content teaser
                title = mention.get("title", "")
                content = mention.get("content_teaser", "")
                text = f"{title}. {content}".strip()
                
                tasks.append(self._check_single_relevance(client, text, context, i))

            # Run all tasks in parallel
            results = await asyncio.gather(*tasks)

        # Process results
        # results is a list of tuples (index, is_relevant)
        # We sort by index just to be safe, though gather usually preserves order of tasks list
        results.sort(key=lambda x: x[0])

        relevant_mentions = []
        filtered_count = 0

        for i, is_relevant in results:
            if is_relevant:
                relevant_mentions.append(mentions[i])
            else:
                filtered_count += 1
                logger.debug(f"Filtered out: {mentions[i].get('title', '')[:50]}...")

        if filtered_count > 0:
            logger.info(f"✅ AI Filter complete: Kept {len(relevant_mentions)}/{len(mentions)} ({filtered_count} removed)")
        else:
            logger.info(f"✅ AI Filter complete: All {len(mentions)} mentions passed relevance check")

        return relevant_mentions


# Singleton instance for easy import
relevance_filter = RelevanceFilter()