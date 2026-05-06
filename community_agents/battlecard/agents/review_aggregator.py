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
_RATING_RE = re.compile(r"(\d\.\d|\d)\s*/\s*5|(\d\.\d|\d)\s+out\s+of\s+5|rating[:\s]+(\d[\.\d]*)", re.I)
_COUNT_RE = re.compile(r"([\d,]+)\s+(?:reviews?|ratings?)", re.I)


class ReviewAggregatorAgent(BaseAgent):
    """
    Scrapes public review profiles on G2, Capterra, Trustpilot, and ProductHunt.

    Input: ``{"company_name": "...", "domain": "..."}``
    """

    name = "review_aggregator"
    description = "Scrapes public ratings and review counts from G2, Capterra, Trustpilot, ProductHunt."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict")

        name = context.input.get("company_name") or context.input.get("name") or ""
        domain = context.input.get("domain", "")

        if not name and not domain:
            return AgentResult.exception(agent=self.name, reason="Missing 'company_name' or 'domain'")

        query = name or domain.split(".")[0]

        payload = {
            "g2": self._scrape_g2(query),
            "capterra": self._scrape_capterra(query),
            "trustpilot": self._scrape_trustpilot(domain or query),
            "producthunt": self._scrape_producthunt(query),
        }

        logger.info("review_aggregator: scraped 4 platforms for '%s'", query)
        return AgentResult.passed(agent=self.name, payload=payload)

    def _scrape_g2(self, query: str) -> dict[str, Any]:
        url = f"https://www.g2.com/search?query={quote_plus(query)}"
        html, _ = fetch(url)
        if not html:
            return _ND
        soup = BeautifulSoup(html, "lxml")
        card = soup.find(attrs={"class": re.compile(r"product-card|search-result", re.I)})
        if not card:
            return _ND
        rating = self._extract_rating(card.get_text(" "))
        count = self._extract_count(card.get_text(" "))
        pros = [li.get_text(strip=True) for li in card.find_all("li")[:3]]
        return {"rating": rating, "review_count": count, "top_highlights": pros or _ND}

    def _scrape_capterra(self, query: str) -> dict[str, Any]:
        url = f"https://www.capterra.com/search/?query={quote_plus(query)}"
        html, _ = fetch(url)
        if not html:
            return _ND
        soup = BeautifulSoup(html, "lxml")
        card = soup.find(attrs={"class": re.compile(r"product|listing|card", re.I)})
        if not card:
            return _ND
        text = card.get_text(" ")
        return {"rating": self._extract_rating(text), "review_count": self._extract_count(text)}

    def _scrape_trustpilot(self, domain: str) -> dict[str, Any]:
        clean = domain.replace("www.", "").split(".")[0]
        url = f"https://www.trustpilot.com/search?query={quote_plus(clean)}"
        html, _ = fetch(url)
        if not html:
            return _ND
        soup = BeautifulSoup(html, "lxml")
        card = soup.find(attrs={"class": re.compile(r"businessUnitResult|search-result|card", re.I)})
        if not card:
            return _ND
        text = card.get_text(" ")
        return {"rating": self._extract_rating(text), "review_count": self._extract_count(text)}

    def _scrape_producthunt(self, query: str) -> dict[str, Any]:
        url = f"https://www.producthunt.com/search?q={quote_plus(query)}"
        html, _ = fetch(url)
        if not html:
            return _ND
        soup = BeautifulSoup(html, "lxml")
        card = soup.find(attrs={"data-test": re.compile(r"post|product", re.I)}) or soup.find(
            attrs={"class": re.compile(r"post|product", re.I)}
        )
        if not card:
            return _ND
        votes = re.search(r"(\d[\d,]*)\s*(?:votes?|upvotes?)", card.get_text(" "), re.I)
        return {
            "upvotes": votes.group(1).replace(",", "") if votes else _ND,
            "url": f"https://www.producthunt.com/search?q={quote_plus(query)}",
        }

    def _extract_rating(self, text: str) -> str | dict:
        m = _RATING_RE.search(text)
        if m:
            return next(g for g in m.groups() if g)
        return _ND

    def _extract_count(self, text: str) -> str | dict:
        m = _COUNT_RE.search(text)
        if m:
            return m.group(1).replace(",", "")
        return _ND
