from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

from community_agents.battlecard._http import fetch_json
from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_ND: dict[str, Any] = {"data": None, "note": "Not enough public data"}

_HN_STORY_URL = "https://hn.algolia.com/api/v1/search?query={q}&tags=story&hitsPerPage=15"
_HN_COMMENT_URL = "https://hn.algolia.com/api/v1/search?query={q}&tags=comment&hitsPerPage=20"

_POS = frozenset(["great", "love", "best", "amazing", "recommend", "easy", "impressive", "solid", "excellent"])
_NEG = frozenset(["bad", "terrible", "worst", "avoid", "broken", "expensive", "overpriced", "scam", "disappointing", "buggy"])

# Query intents: general + specific angles
_QUERY_INTENTS = ["{q}", "{q} review", "{q} alternative", "{q} pricing", "{q} problems"]


class HackerNewsAgent(BaseAgent):
    """
    Fetches HN discussions via the free Algolia public API — no auth required.
    Runs 5 intent-based queries to surface reviews, alternatives, pricing debates, and complaints.

    Input: ``{"company_name": "...", "domain": "..."}``
    """

    name = "hn_signals"
    description = "Fetches HN stories and comments about the company via Algolia public API."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict")

        name = context.input.get("company_name") or ""
        domain = context.input.get("domain", "")
        q = name or domain.split(".")[0]

        if not q:
            return AgentResult.exception(agent=self.name, reason="Missing 'company_name' or 'domain'")

        stories = self._fetch_stories(q)
        comments = self._fetch_comments(q)

        if not stories and not comments:
            return AgentResult.passed(agent=self.name, payload={"hn": {**_ND, "note": "No HN discussions found"}})

        themes = self._extract_themes(stories, comments)
        sentiment = self._score_sentiment(stories + [{"title": c.get("text", ""), "score": 0} for c in comments])
        ask_hn = [s for s in stories if s.get("title", "").lower().startswith("ask hn")]

        payload = {
            "hn": {
                "story_count": len(stories),
                "comment_count": len(comments),
                "sentiment": sentiment,
                "top_stories": [
                    {"title": s["title"], "points": s.get("points", 0), "comments": s.get("num_comments", 0), "url": s.get("url", "")}
                    for s in sorted(stories, key=lambda x: x.get("points", 0), reverse=True)[:5]
                ],
                "ask_hn_threads": [s["title"] for s in ask_hn[:3]],
                "key_themes": themes,
            }
        }
        logger.info("hn_signals: %d stories, %d comments for '%s'", len(stories), len(comments), q)
        return AgentResult.passed(agent=self.name, payload=payload)

    def _fetch_stories(self, q: str) -> list[dict]:
        seen: set[str] = set()
        results: list[dict] = []
        for template in _QUERY_INTENTS:
            query = template.format(q=q)
            data = fetch_json(_HN_STORY_URL.format(q=quote_plus(query)))
            if not data or not isinstance(data, dict):
                continue
            for hit in data.get("hits", []):
                oid = hit.get("objectID", "")
                if oid and oid not in seen:
                    seen.add(oid)
                    results.append(hit)
        return results

    def _fetch_comments(self, q: str) -> list[dict]:
        data = fetch_json(_HN_COMMENT_URL.format(q=quote_plus(q)))
        if not data or not isinstance(data, dict):
            return []
        return [h for h in data.get("hits", []) if h.get("comment_text") or h.get("text")]

    def _extract_themes(self, stories: list[dict], comments: list[dict]) -> list[str]:
        all_text = " ".join(
            s.get("title", "") for s in stories
        ) + " ".join(
            (c.get("comment_text") or c.get("text") or "") for c in comments[:10]
        )
        all_text = all_text.lower()
        themes = []
        _THEME_PATTERNS = {
            "pricing / cost concerns": r"\bpric(e|ing)\b|\bcost\b|\bexpensiv\b|\baffordab\b",
            "performance / reliability": r"\bslow\b|\bfast\b|\bperformanc\b|\blatency\b|\breliab\b|\buptime\b",
            "alternative / switching": r"\balternativ\b|\bswitch\b|\bmigrat\b|\bleav\b|\bmov(e|ing) (away|from)\b",
            "customer support": r"\bsupport\b|\bservice\b|\bresponse time\b|\bhelp\b",
            "enterprise / scaling": r"\benterprise\b|\bscal\b|\blarge team\b|\borganization\b",
            "open source / self-host": r"\bopen.?sourc\b|\bself.?host\b|\bon.?prem\b",
            "AI / ML features": r"\bai\b|\bmachine learning\b|\bllm\b|\bgpt\b|\bml\b",
            "security / compliance": r"\bsecurity\b|\bcomplianc\b|\bsoc2\b|\bgdpr\b",
        }
        for theme, pattern in _THEME_PATTERNS.items():
            if re.search(pattern, all_text):
                themes.append(theme)
        return themes

    def _score_sentiment(self, items: list[dict]) -> str:
        pos = neg = 0
        for item in items:
            words = set((item.get("title") or "").lower().split())
            pos += len(words & _POS)
            neg += len(words & _NEG)
        if pos == 0 and neg == 0:
            return "neutral"
        if pos > neg * 1.5:
            return "positive"
        if neg > pos * 1.5:
            return "negative"
        return "mixed"
