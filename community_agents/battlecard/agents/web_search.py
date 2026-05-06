from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote_plus

import requests

from community_agents.battlecard._http import fetch_json
from swarm_core.base import AgentContext, AgentResult, BaseAgent, DecisionSource
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_ND: dict[str, Any] = {"data": None, "note": "Not enough public data"}

_PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
_DDG_URL = "https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Chakra47-Battlecard/1.0)",
    "Accept": "application/json",
}


def _perplexity_search(query: str, api_key: str) -> dict[str, Any]:
    """Call Perplexity sonar model — real-time web search with citations."""
    try:
        resp = requests.post(
            _PERPLEXITY_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": query}],
                "max_tokens": 1024,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        citations = data.get("citations", [])
        return {"answer": content, "citations": citations[:5], "source": "perplexity"}
    except Exception as exc:
        logger.debug("web_search: perplexity failed for '%s' — %s", query[:60], exc)
        return {}


def _ddg_search(query: str) -> dict[str, Any]:
    """DuckDuckGo Instant Answer API — free fallback, no key needed."""
    data = fetch_json(_DDG_URL.format(q=quote_plus(query)))
    if not data or not isinstance(data, dict):
        return {}
    abstract = data.get("AbstractText", "").strip()
    answer = data.get("Answer", "").strip()
    content = abstract or answer
    if not content:
        # Try related topics
        topics = data.get("RelatedTopics", [])
        snippets = [t.get("Text", "") for t in topics[:3] if isinstance(t, dict) and t.get("Text")]
        content = " | ".join(snippets)
    if not content:
        return {}
    return {
        "answer": content[:600],
        "citations": [data.get("AbstractURL", "")],
        "source": "duckduckgo",
    }


class WebSearchAgent(BaseAgent):
    """
    Runs targeted web searches for each research sub-question.

    Uses Perplexity AI API when PERPLEXITY_API_KEY is set in .env — real-time
    web search with citations. Falls back to DuckDuckGo Instant Answer (free).

    This agent is the intelligence layer that bypasses JS-rendering issues and
    fills what scraping cannot reach (B2C companies, blocked sites, etc.).

    Input:  ``{"queries": [{"id": "...", "q": "..."}], "company_name": "..."}``
    Output: ``{"results": {"pricing": {"answer": "...", "citations": [...], "source": "..."}, ...}}``
    """

    name = "web_search"
    description = "Runs targeted research queries via Perplexity AI (or DDG fallback)."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict with 'queries'")

        queries: list[dict] = context.input.get("queries", [])
        if not queries:
            return AgentResult.exception(agent=self.name, reason="No queries provided")

        api_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
        use_perplexity = bool(api_key)
        source = DecisionSource.CODE

        results: dict[str, Any] = {}
        hits = misses = 0

        for item in queries:
            qid = item.get("id", f"q{len(results)}")
            q = item.get("q", "")
            if not q:
                continue

            if use_perplexity:
                result = _perplexity_search(q, api_key)
            else:
                result = _ddg_search(q)

            if result:
                results[qid] = result
                hits += 1
            else:
                results[qid] = _ND
                misses += 1

        if hits > 0:
            source = DecisionSource.LLM if use_perplexity else DecisionSource.CODE

        engine = "Perplexity" if use_perplexity else "DuckDuckGo"
        logger.info(
            "web_search: %d/%d hits via %s for %d queries",
            hits, hits + misses, engine, len(queries),
        )
        return AgentResult.passed(
            agent=self.name,
            payload={
                "results": results,
                "engine": engine,
                "hits": hits,
                "misses": misses,
            },
            source=source,
        )
