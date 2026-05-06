from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from community_agents.battlecard._http import fetch
from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_ND: dict[str, Any] = {"data": None, "note": "Not enough public data"}
_RATING_RE = re.compile(r"(\d\.\d|\d)\s*(?:stars?|/\s*5|out\s+of\s+5)", re.I)
_COUNT_RE = re.compile(r"([\d,]+)\s+(?:Google\s+)?reviews?", re.I)


class GoogleReviewsAgent(BaseAgent):
    """
    Attempts to extract Google Business / Maps rating from public search results.
    Falls back to 'Not enough public data' when JS rendering is required.

    Input: ``{"company_name": "...", "domain": "..."}``
    """

    name = "google_reviews"
    description = "Best-effort extraction of Google rating from search result meta."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict")

        name = context.input.get("company_name") or context.input.get("name") or ""
        domain = context.input.get("domain", "")

        if not name and not domain:
            return AgentResult.exception(agent=self.name, reason="Missing 'company_name' or 'domain'")

        query = f"{name} reviews" if name else f"{domain} reviews"
        result = self._search_google(query)

        logger.info("google_reviews: result for '%s' → %s", query, result)
        return AgentResult.passed(agent=self.name, payload={"google_reviews": result})

    def _search_google(self, query: str) -> dict[str, Any]:
        # Google blocks most scrapers; we try but gracefully return ND on failure.
        url = f"https://www.google.com/search?q={quote_plus(query)}&hl=en"
        html, _ = fetch(url)
        if not html:
            return {**_ND, "note": "Google blocked the request — requires browser rendering"}

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)

        rating = self._extract_rating(text)
        count = self._extract_count(text)

        if isinstance(rating, dict) and isinstance(count, dict):
            return {**_ND, "note": "Rating not found in static HTML — Google renders this with JavaScript"}

        return {
            "rating": rating,
            "review_count": count,
            "source": "Google Search snippet (static)",
        }

    def _extract_rating(self, text: str) -> str | dict:
        m = _RATING_RE.search(text)
        return m.group(1) if m else _ND

    def _extract_count(self, text: str) -> str | dict:
        m = _COUNT_RE.search(text)
        return m.group(1).replace(",", "") if m else _ND
