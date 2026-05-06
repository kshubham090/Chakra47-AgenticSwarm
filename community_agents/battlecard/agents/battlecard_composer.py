from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from swarm_core.base import AgentContext, AgentResult, BaseAgent, DecisionSource
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_ND: dict[str, Any] = {"data": None, "note": "Not enough public data"}

try:
    import ollama as _ollama
    _OLLAMA_OK = True
except ImportError:
    _OLLAMA_OK = False

try:
    from swarm_core.config import OLLAMA_MODEL as _MODEL
except Exception:
    _MODEL = "llama3.2"


def _is_nd(v: Any) -> bool:
    return isinstance(v, dict) and "data" in v and v["data"] is None


def _ask_llm(prompt: str, temperature: float = 0.2) -> str | None:
    if not _OLLAMA_OK:
        return None
    try:
        resp = _ollama.chat(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": temperature},
        )
        return resp["message"]["content"].strip()
    except Exception as exc:
        logger.debug("composer: ollama failed — %s", exc)
        return None


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return None


def _pick(web: dict, *query_ids: str) -> str | None:
    """Return first non-empty answer from web search results."""
    for qid in query_ids:
        r = web.get(qid, {})
        if isinstance(r, dict) and r.get("answer"):
            return r["answer"]
    return None


def _citations(web: dict, *query_ids: str) -> list[str]:
    for qid in query_ids:
        r = web.get(qid, {})
        if isinstance(r, dict) and r.get("citations"):
            return [c for c in r["citations"] if c][:3]
    return []


class BattlecardComposerAgent(BaseAgent):
    """
    3-phase intelligence composer (gpt-researcher pattern):
      1. Code assembles all scraped + web-search signals
      2. LLM produces structured strategic analysis across all signals
      3. Code derives deterministic battle angles from signal patterns

    Output format: strategic battlecard with confidence scores and source attribution.

    Input: all agent payloads + user_context + web_search results.
    """

    name = "battlecard_composer"
    description = "Ranks signals, gap-fills via web search, and synthesizes a strategic battlecard."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict of agent payloads")

        d = context.input
        user_ctx = d.get("user_context", {})
        web = d.get("web_search", {}).get("results", {})
        engine = d.get("web_search", {}).get("engine", "none")

        company_name = self._resolve_name(d, web)

        # Phase 1 — assemble ranked signals (code, deterministic)
        card = self._assemble(d, company_name, web)
        card["meta"] = {
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "company": company_name,
            "search_engine": engine,
            "web_queries_answered": d.get("web_search", {}).get("hits", 0),
            "confidence": self._confidence_score(card, web),
        }

        source = DecisionSource.CODE

        # Phase 2 — LLM strategic synthesis across ALL ranked signals
        if _OLLAMA_OK:
            print("[battlecard] LLM strategic synthesis (cross-referencing all signals) ...")
            signals_ctx = self._build_signals_context(card, web)
            raw = _ask_llm(self._strategy_prompt(company_name, user_ctx, signals_ctx))
            strategy = _parse_json(raw)
            card["strategic_analysis"] = strategy or {"note": "LLM synthesis returned unparseable output", "raw": raw}
            source = DecisionSource.LLM
        else:
            card["strategic_analysis"] = {"note": "Start Ollama (ollama serve) for AI strategic analysis"}

        # Phase 3 — deterministic battle angles (always run, no LLM needed)
        card["our_angle"] = self._code_angles(user_ctx, card, web)

        logger.info("composer: assembled for '%s' | engine=%s | source=%s", company_name, engine, source.value)
        return AgentResult.passed(agent=self.name, payload=card, source=source)

    # ── name resolution ────────────────────────────────────────────────────────

    def _resolve_name(self, d: dict, web: dict) -> str:
        scraped = d.get("company", {}).get("name")
        if isinstance(scraped, str) and 0 < len(scraped) < 60:
            bad = {"blocked", "request", "denied", "error", "captcha", "security", "cookie", "unknown"}
            if not any(w in scraped.lower() for w in bad):
                return scraped
        # Try web search snapshot
        snapshot = _pick(web, "snapshot", "leadership")
        if snapshot:
            m = re.search(r"^([A-Z][A-Za-z0-9\s&.,']+?)(?:\s+is\b|\s+was\b|[,\.])", snapshot)
            if m:
                return m.group(1).strip()
        domain = d.get("company", {}).get("url", "").replace("https://", "").split(".")[0]
        return domain.capitalize() or "Unknown"

    # ── signal assembly ────────────────────────────────────────────────────────

    def _assemble(self, d: dict, company_name: str, web: dict) -> dict[str, Any]:
        co = d.get("company", {})
        tech = d.get("tech_stack", {})
        pr = d.get("pricing", {})
        cl = d.get("clients", {})
        rev = d.get("reviews", {})
        soc = d.get("social", {})
        red = d.get("reddit", {}).get("reddit", _ND)
        hn = d.get("hn", {}).get("hn", _ND)
        car = d.get("careers", {})
        goog = d.get("google_reviews", {})

        # Web search enriches every ND field
        def ws(scraped: Any, *qids: str) -> Any:
            """Return scraped value if available, else web search answer."""
            if not _is_nd(scraped) and scraped:
                return scraped
            ans = _pick(web, *qids)
            return ans or scraped

        return {
            "snapshot": {
                "name": company_name,
                "tagline": ws(co.get("tagline", _ND), "snapshot", "products"),
                "founded": ws(co.get("founded", _ND), "snapshot"),
                "hq": ws(co.get("location", _ND), "snapshot"),
                "revenue_stage": ws(_ND, "revenue"),
                "employee_count": ws(co.get("employee_count", _ND), "snapshot"),
                "size_estimate": car.get("size_estimate", _ND),
                "growth_signal": ws(car.get("growth_signal", _ND), "strategy"),
                "sources": _citations(web, "snapshot", "revenue"),
            },
            "product_intel": {
                "core_offering": ws(_ND, "products"),
                "key_features": ws(_ND, "products"),
                "tech_stack": ws(tech.get("tech_stack") or _ND, "tech_stack"),
                "marketing_tools": tech.get("marketing_tools") or _ND,
                "marketing_strategy": ws(tech.get("marketing_strategy_signals") or _ND, "marketing"),
                "pricing_model": ws(pr.get("pricing_model", _ND), "pricing"),
                "pricing_detail": ws(_ND, "pricing"),
                "free_tier": pr.get("free_tier", _ND),
                "contact_sales": pr.get("contact_sales", _ND),
                "sources": _citations(web, "pricing", "products", "tech_stack"),
            },
            "market_position": {
                "positioning": ws(_ND, "competitors"),
                "target_segments": ws(_ND, "clients", "products"),
                "known_clients": ws(cl.get("known_clients", _ND), "clients"),
                "case_study_count": cl.get("case_study_count", _ND),
                "main_competitors": ws(_ND, "competitors"),
                "leadership": ws(_ND, "leadership"),
                "sources": _citations(web, "clients", "competitors", "leadership"),
            },
            "sentiment_map": {
                "overall": self._overall_sentiment(red, hn),
                "reddit": red,
                "hackernews": hn,
                "review_platforms": {
                    "g2": rev.get("g2", _ND),
                    "capterra": rev.get("capterra", _ND),
                    "trustpilot": rev.get("trustpilot", _ND),
                    "producthunt": rev.get("producthunt", _ND),
                    "google": goog.get("google_reviews", _ND),
                },
                "customer_complaints_web": ws(_ND, "complaints", "weaknesses"),
                "customer_praise_web": ws(_ND, "strengths"),
                "recent_controversies": ws(_ND, "controversies"),
                "sources": _citations(web, "complaints", "strengths", "controversies"),
            },
            "hiring_signals": {
                "open_roles": car.get("open_roles", _ND),
                "departments": car.get("departments", _ND),
                "tech_signals": car.get("tech_signals", _ND),
            },
            "social": soc.get("profiles", _ND),
        }

    def _overall_sentiment(self, reddit: Any, hn: Any) -> str:
        scores = []
        if isinstance(reddit, dict) and reddit.get("sentiment"):
            scores.append(reddit["sentiment"])
        if isinstance(hn, dict) and hn.get("sentiment"):
            scores.append(hn["sentiment"])
        if not scores:
            return "unknown"
        neg = sum(1 for s in scores if s == "negative")
        pos = sum(1 for s in scores if s == "positive")
        if neg > pos:
            return "negative"
        if pos > neg:
            return "positive"
        return "mixed"

    def _confidence_score(self, card: dict, web: dict) -> str:
        hits = sum(1 for v in web.values() if isinstance(v, dict) and v.get("answer"))
        reddit_ok = not _is_nd(card.get("sentiment_map", {}).get("reddit", _ND))
        hn_ok = not _is_nd(card.get("sentiment_map", {}).get("hackernews", _ND))
        score = hits + (3 if reddit_ok else 0) + (2 if hn_ok else 0)
        if score >= 10:
            return "high"
        if score >= 5:
            return "medium"
        return "low"

    # ── signal context for LLM ────────────────────────────────────────────────

    def _build_signals_context(self, card: dict, web: dict) -> str:
        lines: list[str] = []
        snap = card.get("snapshot", {})
        lines.append(f"COMPANY: {snap.get('name')} | Founded: {snap.get('founded')} | HQ: {snap.get('hq')}")
        lines.append(f"Revenue/Stage: {snap.get('revenue_stage')} | Employees: {snap.get('employee_count')}")

        prod = card.get("product_intel", {})
        lines.append(f"Core offering: {prod.get('core_offering')}")
        lines.append(f"Tech stack: {prod.get('tech_stack')}")
        lines.append(f"Pricing: {prod.get('pricing_model')} — {prod.get('pricing_detail')}")

        mkt = card.get("market_position", {})
        lines.append(f"Target segments: {mkt.get('target_segments')}")
        lines.append(f"Competitors: {mkt.get('main_competitors')}")
        lines.append(f"Known clients: {mkt.get('known_clients')}")

        sent = card.get("sentiment_map", {})
        reddit = sent.get("reddit", {})
        if isinstance(reddit, dict) and not _is_nd(reddit):
            lines.append(f"Reddit ({reddit.get('mention_count')} mentions, {reddit.get('sentiment')})")
            lines.append(f"  Pain points: {reddit.get('pain_points')}")
            lines.append(f"  Switching triggers: {reddit.get('switching_triggers')}")
        hn = sent.get("hackernews", {})
        if isinstance(hn, dict) and not _is_nd(hn):
            lines.append(f"HN ({hn.get('story_count')} stories, {hn.get('sentiment')}, themes={hn.get('key_themes')})")

        lines.append(f"Complaints (web): {sent.get('customer_complaints_web')}")
        lines.append(f"Praise (web): {sent.get('customer_praise_web')}")
        lines.append(f"Controversies: {sent.get('recent_controversies')}")
        lines.append(f"Strategy: {_pick(web, 'strategy')}")
        return "\n".join(str(l) for l in lines)

    def _strategy_prompt(self, company: str, user_ctx: dict, signals: str) -> str:
        return (
            f"You are an elite competitive intelligence analyst.\n\n"
            f"COMPETITOR: {company}\n"
            f"OUR COMPANY: {user_ctx.get('company_name','us')} — {user_ctx.get('what_you_do','')}\n"
            f"OUR ICP: {user_ctx.get('icp','')}\n"
            f"OUR DIFFERENTIATORS: {', '.join(user_ctx.get('differentiators',[]))}\n\n"
            f"SIGNALS:\n{signals}\n\n"
            "Produce strategic analysis. Return ONLY valid JSON:\n"
            '{"core_strengths":["evidence-based, max 5"],'
            '"key_weaknesses":["evidence-based, max 5"],'
            '"market_positioning":"1 sentence",'
            '"customer_pain_points":["from reviews/reddit/web"],'
            '"switching_triggers":["reasons customers leave"],'
            '"battle_angles":[{"angle":"...","evidence":"cite source","how_to_use":"exact talk track"}],'
            '"hidden_patterns":["non-obvious cross-source insights"],'
            '"market_gaps":["opportunities they miss"],'
            '"recommended_actions":["3 specific next steps for our sales team"]}'
        )

    # ── deterministic angles ──────────────────────────────────────────────────

    def _code_angles(self, user_ctx: dict, card: dict, web: dict) -> list[dict[str, str]]:
        angles: list[dict[str, str]] = []
        diffs = " ".join(user_ctx.get("differentiators", [])).lower()
        prod = card.get("product_intel", {})
        sent = card.get("sentiment_map", {})
        reddit = sent.get("reddit", {})
        hn = sent.get("hackernews", {})

        if not _is_nd(prod.get("contact_sales")) and prod.get("contact_sales") and "transparent pricing" in diffs:
            angles.append({"angle": "Pricing transparency", "evidence": "They require sales contact for pricing",
                           "talk_track": "Ask: 'How long did it take you to get pricing from them? We publish everything online.'"})

        if not _is_nd(prod.get("free_tier")) and not prod.get("free_tier") and "free" in diffs:
            angles.append({"angle": "Lower barrier to try", "evidence": "No free tier detected",
                           "talk_track": "Start them on our free tier — zero procurement friction vs their sales cycle."})

        if isinstance(reddit, dict) and reddit.get("sentiment") in ("negative", "mixed"):
            pts = reddit.get("pain_points", [])
            if pts:
                angles.append({"angle": f"Community frustration: {pts[0]}", "evidence": f"Reddit: {reddit.get('mention_count')} mentions, sentiment={reddit.get('sentiment')}",
                               "talk_track": f"'We've heard from customers who switched from them over {pts[0].lower()} — what's your experience been?'"})

        if isinstance(reddit, dict):
            for t in (reddit.get("switching_triggers") or []):
                angles.append({"angle": f"Switching trigger: {t}", "evidence": "Reddit multi-query analysis",
                               "talk_track": f"'We're seeing a wave of teams switching over {t.lower()} — is that a concern for you?'"})

        if isinstance(hn, dict) and "pricing / cost concerns" in (hn.get("key_themes") or []):
            angles.append({"angle": "HN: pricing is a recurring debate", "evidence": "HackerNews key themes",
                           "talk_track": "Lead with TCO comparison — HN community flags their pricing repeatedly."})

        controversies = sent.get("recent_controversies")
        if controversies and not _is_nd(controversies):
            angles.append({"angle": "Recent controversies create doubt", "evidence": controversies[:200],
                           "talk_track": "If prospect raises it: 'We've seen that too — here's how we handle it differently.'"})

        if not angles:
            angles.append({"angle": "Set your differentiators in the CLI prompt", "evidence": "N/A",
                           "talk_track": "Provide differentiators at startup for context-aware battle angles."})
        return angles
