from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_ND: dict[str, Any] = {"data": None, "note": "Not enough public data"}

_PRICE_RE = re.compile(
    r"\$\s*(\d[\d,]*(?:\.\d{2})?)\s*(?:/\s*(?:mo(?:nth)?|yr|year|user|seat|month))?",
    re.IGNORECASE,
)
_TIER_NAMES = [
    "free", "starter", "basic", "standard", "essential", "lite",
    "pro", "professional", "growth", "scale", "business",
    "team", "plus", "premium", "advanced", "enterprise", "ultimate",
]
_CONTACT_RE = re.compile(r"contact\s+(?:us|sales)|talk\s+to\s+(?:us|sales)|custom\s+pricing|get\s+a\s+quote", re.I)
_FREE_RE = re.compile(
    r"\bfree\s+(?:plan|tier|forever|trial)|\bfreemium\b|free\s+for\s+(?:up\s+to|ever)|\$0(?:/mo|\s|$)",
    re.I,
)


class PricingAgent(BaseAgent):
    """
    Extracts pricing model, tiers, and price points from a pricing page.

    Input: ``{"html": "<pricing page html>", "pricing_url": "..."}``
    """

    name = "pricing_extractor"
    description = "Extracts pricing model, tiers, and price points from a pricing page."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict with 'html'")

        html = context.input.get("html") or ""

        if not html:
            return AgentResult.passed(
                agent=self.name,
                payload={"pricing_model": _ND, "tiers": _ND, "free_tier": _ND, "contact_sales": _ND},
            )

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)

        tiers = self._extract_tiers(soup, text)
        prices = self._extract_prices(text)
        pricing_model = self._infer_model(text, prices)
        has_free = bool(_FREE_RE.search(text))
        has_contact = bool(_CONTACT_RE.search(text))

        logger.info(
            "pricing_extractor: model=%s, tiers=%d, free=%s, contact=%s",
            pricing_model, len(tiers), has_free, has_contact,
        )
        return AgentResult.passed(
            agent=self.name,
            payload={
                "pricing_model": pricing_model or _ND,
                "tiers": tiers or _ND,
                "price_points": prices or _ND,
                "free_tier": has_free,
                "contact_sales": has_contact,
            },
        )

    def _extract_tiers(self, soup: BeautifulSoup, text: str) -> list[str]:
        found = []
        lower = text.lower()
        for name in _TIER_NAMES:
            if re.search(rf"\b{name}\b", lower):
                found.append(name.capitalize())
        # Also look for heading tags that might name tiers
        for tag in soup.find_all(["h2", "h3", "h4"]):
            t = tag.get_text(strip=True).lower()
            for name in _TIER_NAMES:
                if name == t and name.capitalize() not in found:
                    found.append(name.capitalize())
        return list(dict.fromkeys(found))  # dedupe, preserve order

    def _extract_prices(self, text: str) -> list[str]:
        matches = _PRICE_RE.findall(text)
        seen: set[str] = set()
        prices = []
        for m in matches:
            val = f"${m}"
            if val not in seen:
                seen.add(val)
                prices.append(val)
        return prices[:10]

    def _infer_model(self, text: str, prices: list[str]) -> str | None:
        lower = text.lower()
        if re.search(r"\bper\s+(?:user|seat|member)\b", lower):
            return "per_seat"
        if re.search(r"\bper\s+(?:request|api\s+call|message|credit|event)\b", lower):
            return "usage_based"
        if re.search(r"contact\s+(?:us|sales)|custom\s+pricing", lower, re.I):
            return "contact_sales"
        if _FREE_RE.search(text) and prices:
            return "freemium"
        if prices:
            return "flat_rate"
        return None
