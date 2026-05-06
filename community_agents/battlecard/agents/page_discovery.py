from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from community_agents.battlecard._http import fetch
from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_ND = {"data": None, "note": "Not enough public data"}

_CATEGORIES: dict[str, list[str]] = {
    "pricing": ["pricing", "plans", "price", "cost", "buy", "billing", "subscribe"],
    "about": ["about", "company", "who-we-are", "mission", "story", "team"],
    "features": ["features", "product", "solutions", "capabilities", "platform", "how-it-works"],
    "blog": ["blog", "news", "insights", "resources", "articles", "learn"],
    "careers": ["careers", "jobs", "hiring", "join", "work-with-us", "open-positions"],
    "customers": ["customers", "clients", "case-studies", "success", "testimonials", "partners"],
    "press": ["press", "media", "newsroom", "announcements"],
    "contact": ["contact", "support", "help", "demo", "talk-to-us", "get-started"],
}


class PageDiscoveryAgent(BaseAgent):
    """
    Discovers key pages on a competitor's website via sitemap.xml and nav links.

    Input: ``{"url": "https://example.com", "html": "<homepage html>", "headers": {}}``
    """

    name = "page_discovery"
    description = "Discovers and categorizes key pages via sitemap.xml and homepage nav links."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict with 'url'")

        url = context.input.get("url", "")
        html = context.input.get("html") or ""

        if not url:
            return AgentResult.exception(agent=self.name, reason="Missing required key: 'url'")

        parsed = urlparse(url)
        domain = parsed.netloc
        base_url = f"{parsed.scheme}://{domain}"

        sitemap_urls = self._parse_sitemap(base_url)
        nav_urls = self._extract_nav_links(html, base_url)
        all_urls = list({*sitemap_urls, *nav_urls})
        discovered = self._categorize(all_urls, base_url)

        logger.info("page_discovery: found %d urls, categorized %d pages", len(all_urls), len(discovered))
        return AgentResult.passed(
            agent=self.name,
            payload={
                "domain": domain,
                "base_url": base_url,
                "discovered_pages": discovered,
                "total_urls_found": len(all_urls),
            },
        )

    def _parse_sitemap(self, base_url: str) -> list[str]:
        urls: list[str] = []
        for path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/"]:
            html, _ = fetch(f"{base_url}{path}")
            if not html:
                continue
            try:
                root = ElementTree.fromstring(html)
                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                for loc in root.findall(".//sm:loc", ns):
                    if loc.text:
                        urls.append(loc.text.strip())
                if urls:
                    break
            except ElementTree.ParseError:
                pass
        return urls[:200]

    def _extract_nav_links(self, html: str, base_url: str) -> list[str]:
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if href.startswith(("mailto:", "tel:", "#", "javascript:")):
                continue
            full = urljoin(base_url, href)
            if urlparse(full).netloc == urlparse(base_url).netloc:
                urls.append(full)
        return list(set(urls))

    def _categorize(self, urls: list[str], base_url: str) -> dict[str, str]:
        discovered: dict[str, str] = {}
        for url in urls:
            path = urlparse(url).path.lower().strip("/")
            for category, keywords in _CATEGORIES.items():
                if category not in discovered:
                    for kw in keywords:
                        if re.search(rf"\b{re.escape(kw)}\b", path):
                            discovered[category] = url
                            break
        return discovered
