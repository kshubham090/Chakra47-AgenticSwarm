from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_ND: dict[str, Any] = {"data": None, "note": "Not enough public data"}


class CompanyProfileAgent(BaseAgent):
    """
    Extracts company identity from homepage HTML.

    Input: ``{"url": "...", "html": "<homepage html>", "headers": {}}``
    """

    name = "company_profile"
    description = "Extracts company name, tagline, description, and identity from homepage HTML."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict with 'html'")

        html = context.input.get("html") or ""
        url = context.input.get("url", "")

        if not html:
            return AgentResult.passed(agent=self.name, payload={"name": _ND, "tagline": _ND})

        soup = BeautifulSoup(html, "lxml")
        og = self._extract_og(soup)
        ld = self._extract_json_ld(soup)
        basic = self._extract_basic(soup)

        name = ld.get("name") or og.get("site_name") or og.get("title") or basic.get("title") or _ND
        tagline = (
            og.get("description")
            or ld.get("description")
            or basic.get("meta_description")
            or basic.get("h1")
            or _ND
        )

        payload: dict[str, Any] = {
            "name": name,
            "tagline": tagline,
            "url": url,
            "founded": ld.get("foundingDate") or _ND,
            "location": ld.get("address") or ld.get("location") or _ND,
            "employee_count": ld.get("numberOfEmployees") or _ND,
            "social_links": ld.get("sameAs") or [],
        }

        logger.info("company_profile: extracted '%s'", name if isinstance(name, str) else "unknown")
        return AgentResult.passed(agent=self.name, payload=payload)

    def _extract_og(self, soup: BeautifulSoup) -> dict[str, str]:
        og: dict[str, str] = {}
        for tag in soup.find_all("meta"):
            prop = tag.get("property", "") or tag.get("name", "")
            content = tag.get("content", "")
            if not content:
                continue
            if prop in ("og:title",):
                og["title"] = content
            elif prop in ("og:description", "twitter:description"):
                og["description"] = content
            elif prop == "og:site_name":
                og["site_name"] = content
        return og

    def _extract_json_ld(self, soup: BeautifulSoup) -> dict[str, Any]:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                entries = data if isinstance(data, list) else [data]
                for entry in entries:
                    if isinstance(entry, dict) and entry.get("@type") in (
                        "Organization",
                        "Corporation",
                        "LocalBusiness",
                        "SoftwareApplication",
                    ):
                        return entry
            except (json.JSONDecodeError, AttributeError):
                pass
        return {}

    def _extract_basic(self, soup: BeautifulSoup) -> dict[str, str]:
        out: dict[str, str] = {}
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            raw = title_tag.string.encode("utf-8", "replace").decode("utf-8")
            out["title"] = re.sub(r"\s*[|–—\-·]\s*.*$", "", raw.strip())

        desc = soup.find("meta", attrs={"name": "description"})
        if desc and desc.get("content"):
            out["meta_description"] = desc["content"].strip()

        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            out["h1"] = h1.get_text(strip=True)[:200]

        return out
