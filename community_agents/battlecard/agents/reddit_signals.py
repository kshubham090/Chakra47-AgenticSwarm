from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

from community_agents.battlecard._http import fetch_json
from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_ND: dict[str, Any] = {"data": None, "note": "Not enough public data"}

_POS_WORDS = frozenset([
    "great", "love", "best", "amazing", "excellent", "fantastic",
    "recommend", "easy", "perfect", "awesome", "helpful", "reliable",
    "impressed", "works", "solid", "good",
])
_NEG_WORDS = frozenset([
    "bad", "terrible", "awful", "worst", "horrible", "broken", "expensive",
    "overpriced", "slow", "buggy", "frustrating", "disappointing", "scam",
    "useless", "avoid", "hate", "poor", "trash", "garbage",
])

# Intent-based query templates — surfaces reviews, switching intent, pricing pain, and complaints
_QUERY_TEMPLATES = [
    "{q}",
    "{q} review",
    "{q} alternative",
    "{q} pricing",
    "{q} problem OR issue OR complaint",
]

_BASE = "https://www.reddit.com/search.json?sort=relevance&t=year&limit=20&type=link&q={q}"


class RedditSignalsAgent(BaseAgent):
    """
    Fetches Reddit signals using 5 intent-based query variations.
    Deduplicates across queries and surfaces: sentiment, pain points,
    switching triggers, and community discussion themes.

    Input: ``{"company_name": "...", "domain": "..."}``
    """

    name = "reddit_signals"
    description = "Multi-query Reddit scraper — reviews, alternatives, pricing, and complaints."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict")

        name = context.input.get("company_name") or context.input.get("name") or ""
        domain = context.input.get("domain", "")
        q = name or domain.split(".")[0]

        if not q:
            return AgentResult.exception(agent=self.name, reason="Missing 'company_name' or 'domain'")

        posts = self._fetch_all(q)

        if not posts:
            return AgentResult.passed(
                agent=self.name,
                payload={"reddit": {**_ND, "note": "No Reddit mentions found in the past year"}},
            )

        sentiment = self._score_sentiment(posts)
        pain_points = self._extract_pain_points(posts)
        switching = self._extract_switching_triggers(posts)
        subreddits = self._top_subreddits(posts)
        top_posts = sorted(posts, key=lambda x: x["score"], reverse=True)[:5]

        payload = {
            "reddit": {
                "mention_count": len(posts),
                "sentiment": sentiment,
                "top_subreddits": subreddits,
                "pain_points": pain_points,
                "switching_triggers": switching,
                "top_posts": [
                    {"title": p["title"], "score": p["score"], "subreddit": p["subreddit"]}
                    for p in top_posts
                ],
            }
        }
        logger.info("reddit_signals: %d posts (multi-query), sentiment=%s for '%s'", len(posts), sentiment, q)
        return AgentResult.passed(agent=self.name, payload=payload)

    def _fetch_all(self, q: str) -> list[dict[str, Any]]:
        seen: set[str] = set()
        all_posts: list[dict[str, Any]] = []
        for template in _QUERY_TEMPLATES:
            query = template.format(q=q)
            data = fetch_json(_BASE.format(q=quote_plus(query)))
            if not data or not isinstance(data, dict):
                continue
            for child in data.get("data", {}).get("children", []):
                d = child.get("data", {})
                uid = d.get("id") or (d.get("title", "")[:40] + d.get("subreddit", ""))
                if uid and uid not in seen:
                    seen.add(uid)
                    all_posts.append({
                        "title": d.get("title", ""),
                        "score": d.get("score", 0),
                        "subreddit": d.get("subreddit", ""),
                        "url": d.get("url", ""),
                        "num_comments": d.get("num_comments", 0),
                        "selftext": d.get("selftext", "")[:300],
                    })
        return all_posts

    def _score_sentiment(self, posts: list[dict]) -> str:
        pos = neg = 0
        for p in posts:
            words = set((p["title"] + " " + p.get("selftext", "")).lower().split())
            pos += len(words & _POS_WORDS)
            neg += len(words & _NEG_WORDS)
        if pos == 0 and neg == 0:
            return "neutral"
        if pos > neg * 1.5:
            return "positive"
        if neg > pos * 1.5:
            return "negative"
        return "mixed"

    def _extract_pain_points(self, posts: list[dict]) -> list[str]:
        pain_patterns = {
            "Pricing / too expensive": r"\bexpensiv\b|\bpric(e|ing)\b|\bcost\b|\boverpriced\b",
            "Reliability / downtime": r"\bdown\b|\boutage\b|\bunreliable\b|\bbroken\b|\bbuggy\b",
            "Customer support issues": r"\bsupport\b|\bno response\b|\bignored\b|\bhelp(less)?\b",
            "Missing features": r"\bmissing\b|\bno \w+ feature\b|\bcannot\b|\bdoesn.t support\b",
            "Performance / speed": r"\bslow\b|\blag\b|\bperformanc\b|\blatency\b",
            "Difficult onboarding": r"\bhard to\b|\bcomplex\b|\bconfusing\b|\bsteep learning\b",
        }
        all_text = " ".join(p["title"] + " " + p.get("selftext", "") for p in posts).lower()
        return [label for label, pat in pain_patterns.items() if re.search(pat, all_text)]

    def _extract_switching_triggers(self, posts: list[dict]) -> list[str]:
        triggers = []
        all_text = " ".join(p["title"] for p in posts).lower()
        if re.search(r"\balternativ\b|\bswitch\b|\bmigrat\b|\bleav\b|\bmov(e|ing) (away|from)\b", all_text):
            triggers.append("Users actively seeking alternatives")
        if re.search(r"\btoo expensiv\b|\bprice increase\b|\braised price\b", all_text):
            triggers.append("Pricing changes driving churn")
        if re.search(r"\bacquir\b|\bbought by\b|\bmerge\b", all_text):
            triggers.append("M&A activity causing uncertainty")
        return triggers

    def _top_subreddits(self, posts: list[dict]) -> list[str]:
        counts: dict[str, int] = {}
        for p in posts:
            sr = p["subreddit"]
            if sr:
                counts[sr] = counts.get(sr, 0) + 1
        return [k for k, _ in sorted(counts.items(), key=lambda x: -x[1])][:5]
