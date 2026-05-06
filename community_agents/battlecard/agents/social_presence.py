from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from community_agents.battlecard._http import fetch
from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_ND: dict[str, Any] = {"data": None, "note": "Not enough public data"}

_SOCIAL_RE: dict[str, re.Pattern] = {
    "twitter": re.compile(r"(?:twitter|x)\.com/(?!share|intent|search|home|hashtag)([\w]+)", re.I),
    "linkedin": re.compile(r"linkedin\.com/company/([\w\-]+)", re.I),
    "facebook": re.compile(r"facebook\.com/([\w.\-]+)", re.I),
    "instagram": re.compile(r"instagram\.com/([\w.]+)", re.I),
    "youtube": re.compile(r"youtube\.com/(?:c/|channel/|@)([\w\-]+)", re.I),
    "tiktok": re.compile(r"tiktok\.com/@([\w.]+)", re.I),
    "github": re.compile(r"github\.com/([\w\-]+)", re.I),
    "discord": re.compile(r"discord\.(?:gg|com/invite)/([\w]+)", re.I),
}

_FOLLOWER_RE = re.compile(r"([\d,.]+[KkMm]?)\s*(?:followers?|subscribers?|fans?)", re.I)
_REPO_RE = re.compile(r"(\d+)\s+(?:public\s+)?repositor", re.I)


class SocialPresenceAgent(BaseAgent):
    """
    Detects social profiles from homepage HTML and scrapes basic public metrics.
    Post data that requires authentication is noted explicitly.

    Input: ``{"html": "<homepage html>", "domain": "..."}``
    """

    name = "social_presence"
    description = "Detects social profiles and scrapes public follower counts and channel info."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict with 'html'")

        html = context.input.get("html") or ""
        domain = context.input.get("domain", "")

        if not html:
            return AgentResult.passed(agent=self.name, payload={"profiles": _ND})

        handles = self._detect_profiles(html)
        profiles: dict[str, Any] = {}

        for platform, handle in handles.items():
            profiles[platform] = self._get_profile_data(platform, handle)

        logger.info("social_presence: found %d profiles for %s", len(profiles), domain)
        return AgentResult.passed(agent=self.name, payload={"profiles": profiles or _ND})

    def _detect_profiles(self, html: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "lxml")
        found: dict[str, str] = {}

        # Check footer and header links first, then full HTML
        search_targets = []
        for tag in ["footer", "header", "nav"]:
            el = soup.find(tag)
            if el:
                search_targets.append(el.get_text(" ") + " " + str(el))
        search_targets.append(html)

        for target in search_targets:
            for platform, pattern in _SOCIAL_RE.items():
                if platform not in found:
                    m = pattern.search(target)
                    if m:
                        found[platform] = m.group(1)

        return found

    def _get_profile_data(self, platform: str, handle: str) -> dict[str, Any]:
        scrapers = {
            "youtube": self._scrape_youtube,
            "github": self._scrape_github,
            "twitter": self._scrape_twitter,
        }
        base_urls = {
            "twitter": f"https://twitter.com/{handle}",
            "linkedin": f"https://www.linkedin.com/company/{handle}",
            "facebook": f"https://www.facebook.com/{handle}",
            "instagram": f"https://www.instagram.com/{handle}",
            "youtube": f"https://www.youtube.com/@{handle}",
            "tiktok": f"https://www.tiktok.com/@{handle}",
            "github": f"https://github.com/{handle}",
            "discord": f"https://discord.gg/{handle}",
        }
        profile_url = base_urls.get(platform, "")
        base = {"handle": handle, "url": profile_url}

        scraper = scrapers.get(platform)
        if scraper:
            return {**base, **scraper(handle, profile_url)}
        return {**base, "metrics": {"note": "Post data requires authentication"}}

    def _scrape_youtube(self, handle: str, url: str) -> dict[str, Any]:
        html, _ = fetch(url)
        if not html:
            return {"metrics": _ND}
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ")
        m = _FOLLOWER_RE.search(text)
        return {"subscribers": m.group(1) if m else _ND, "post_data": {"note": "Auth required for post analytics"}}

    def _scrape_github(self, handle: str, url: str) -> dict[str, Any]:
        html, _ = fetch(url)
        if not html:
            return {"metrics": _ND}
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ")
        repos = _REPO_RE.search(text)
        followers = _FOLLOWER_RE.search(text)
        return {
            "public_repos": repos.group(1) if repos else _ND,
            "followers": followers.group(1) if followers else _ND,
            "post_data": {"note": "Public repo activity visible at the URL above"},
        }

    def _scrape_twitter(self, handle: str, url: str) -> dict[str, Any]:
        html, _ = fetch(url)
        if not html:
            return {"metrics": {"note": "Twitter/X requires authentication for most data"}}
        soup = BeautifulSoup(html, "lxml")
        desc = soup.find("meta", attrs={"name": "description"})
        content = desc.get("content", "") if desc else ""
        m = _FOLLOWER_RE.search(content)
        return {
            "followers": m.group(1) if m else _ND,
            "post_data": {"note": "Recent posts require Twitter/X authentication"},
        }
