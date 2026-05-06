from __future__ import annotations

from typing import Any

from community_agents.battlecard._http import fetch
from community_agents.battlecard.agents import (
    BattlecardComposerAgent,
    CareerSignalsAgent,
    ClientEvidenceAgent,
    CompanyProfileAgent,
    GoogleReviewsAgent,
    HackerNewsAgent,
    PageDiscoveryAgent,
    PricingAgent,
    QueryPlannerAgent,
    RedditSignalsAgent,
    ReviewAggregatorAgent,
    SocialPresenceAgent,
    TechStackAgent,
    WebSearchAgent,
)
from swarm_core.base import AgentContext
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_ND: dict[str, Any] = {"data": None, "note": "Not enough public data"}


class BattlecardRunner:
    """
    Orchestrates all battlecard agents for a single competitor URL.
    Pre-fetches the competitor's pages once, then fans out to each agent.
    """

    def run(self, user_context: dict[str, Any], url: str) -> dict[str, Any]:
        url = url.rstrip("/")
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        print(f"\n[battlecard] Fetching homepage: {url}")
        homepage_html, homepage_headers = fetch(url)

        if not homepage_html:
            return {
                "error": (
                    f"Could not fetch {url} — the site blocked the request or is unreachable.\n"
                    "  This is common on enterprise sites (Microsoft, Google, Cloudflare-protected).\n"
                    "  Try a product sub-domain e.g. azure.microsoft.com or docs.company.com instead."
                )
            }

        # Stage 1 — discover key pages
        print("[battlecard] Discovering pages ...")
        discovery = self._run(PageDiscoveryAgent(), {
            "url": url,
            "html": homepage_html,
            "headers": homepage_headers,
        })
        pages = discovery.get("discovered_pages", {})
        domain = discovery.get("domain", "")

        # Stage 2 — fetch key pages
        fetched: dict[str, str | None] = {}
        for page_type in ["pricing", "customers", "careers", "features"]:
            page_url = pages.get(page_type)
            if page_url:
                print(f"[battlecard] Fetching {page_type}: {page_url}")
                html, _ = fetch(page_url)
                fetched[page_type] = html

        # Stage 3 — run extraction agents in parallel logical groups
        print("[battlecard] Extracting company profile ...")
        company = self._run(CompanyProfileAgent(), {
            "url": url, "html": homepage_html, "headers": homepage_headers,
        })
        raw_name = company.get("name") if isinstance(company.get("name"), str) else ""
        import re as _re
        # Strip tagline suffix e.g. "Zomato — India's #1 Food delivery app"
        short_name = _re.split(r"\s*[-–—|·]\s*", raw_name)[0].strip() if raw_name else ""
        # Reject names that look like error/block pages (too long or contain block keywords)
        _POISON = {"blocked", "request", "denied", "error", "captcha", "security", "cookie"}
        name_is_clean = (
            short_name
            and len(short_name) <= 60
            and not any(w in short_name.lower() for w in _POISON)
        )
        company_name = short_name if name_is_clean else domain.split(".")[0].capitalize()

        print("[battlecard] Detecting tech stack & marketing tools ...")
        tech = self._run(TechStackAgent(), {"html": homepage_html, "headers": homepage_headers})

        print("[battlecard] Extracting pricing ...")
        pricing = self._run(PricingAgent(), {"html": fetched.get("pricing"), "pricing_url": pages.get("pricing")})

        print("[battlecard] Scanning for client evidence ...")
        client_ev = self._run(ClientEvidenceAgent(), {
            "homepage_html": homepage_html,
            "customers_html": fetched.get("customers"),
            "case_studies_html": fetched.get("features"),
        })

        print("[battlecard] Scraping review platforms ...")
        reviews = self._run(ReviewAggregatorAgent(), {"company_name": company_name, "domain": domain})

        print("[battlecard] Checking Google reviews ...")
        google_rev = self._run(GoogleReviewsAgent(), {"company_name": company_name, "domain": domain})

        print("[battlecard] Scanning social presence ...")
        social = self._run(SocialPresenceAgent(), {"html": homepage_html, "domain": domain})

        print("[battlecard] Fetching Reddit signals (multi-query) ...")
        reddit = self._run(RedditSignalsAgent(), {"company_name": company_name, "domain": domain})

        print("[battlecard] Fetching Hacker News signals ...")
        hn = self._run(HackerNewsAgent(), {"company_name": company_name, "domain": domain})

        print("[battlecard] Analyzing career signals ...")
        careers = self._run(CareerSignalsAgent(), {"html": fetched.get("careers"), "base_url": url})

        # Stage 4 — plan targeted research queries and execute web search
        print("[battlecard] Planning research queries ...")
        query_plan = self._run(QueryPlannerAgent(), {
            "company_name": company_name,
            "domain": domain,
            "user_context": user_context,
        })
        queries = query_plan.get("queries", [])

        _WS_EMPTY: dict[str, Any] = {"results": {}, "engine": "none", "hits": 0, "misses": 0}
        if queries:
            print(f"[battlecard] Web search ({len(queries)} queries) ...")
            web_search = self._run(WebSearchAgent(), {
                "queries": queries,
                "company_name": company_name,
            })
        else:
            web_search = _WS_EMPTY

        # Stage 5 — compose final battlecard (assembly + LLM gap-fill + strategic synthesis)
        print("[battlecard] Composing battlecard ...")
        battlecard = self._run(BattlecardComposerAgent(), {
            "user_context": user_context,
            "company": company,
            "tech_stack": tech,
            "pricing": pricing,
            "clients": client_ev,
            "reviews": reviews,
            "google_reviews": google_rev,
            "social": social,
            "reddit": reddit,
            "hn": hn,
            "careers": careers,
            "web_search": web_search,
        })

        return battlecard

    def _run(self, agent: Any, input_data: dict[str, Any]) -> dict[str, Any]:
        """Run an agent and return its payload. Returns {} on exception."""
        try:
            result = agent.run(AgentContext(input=input_data))
            return result.payload
        except Exception as exc:
            logger.warning("runner: agent %s failed — %s", agent.name, exc)
            return {}
