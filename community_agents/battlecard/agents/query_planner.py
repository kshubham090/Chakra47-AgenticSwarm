from __future__ import annotations

from typing import Any

from swarm_core.base import AgentContext, AgentResult, BaseAgent, DecisionSource
from swarm_core.utils import get_logger

logger = get_logger(__name__)

# Template sub-questions — used when Ollama is unavailable.
# Each entry: (query_id, question_template)
_TEMPLATES: list[tuple[str, str]] = [
    ("snapshot",      "What is {c}? When was it founded, who founded it, and where is it headquartered?"),
    ("revenue",       "What is {c}'s annual revenue, valuation, and current funding stage?"),
    ("pricing",       "What is {c}'s pricing model? How much does it cost for end users or business customers?"),
    ("tech_stack",    "What technology stack, programming languages, and cloud infrastructure does {c} use?"),
    ("products",      "What are {c}'s main products and key differentiating features?"),
    ("clients",       "Who are {c}'s most notable clients, partners, or enterprise customers?"),
    ("competitors",   "Who are {c}'s main direct competitors and how does {c} compare to them?"),
    ("complaints",    "What are the most common customer complaints and criticisms about {c} in 2024-2025?"),
    ("strengths",     "What are {c}'s key competitive strengths and why do customers choose it?"),
    ("weaknesses",    "What are {c}'s known weaknesses, product gaps, or operational failures?"),
    ("strategy",      "What are {c}'s recent strategic moves, acquisitions, or major announcements in 2024-2025?"),
    ("leadership",    "Who are the key executives at {c} and what is their strategic vision?"),
    ("controversies", "What controversies, lawsuits, or public backlash has {c} faced recently?"),
    ("marketing",     "What marketing channels and growth strategies does {c} use?"),
]

try:
    import ollama as _ollama
    _OLLAMA_OK = True
except ImportError:
    _OLLAMA_OK = False

try:
    from swarm_core.config import OLLAMA_MODEL as _MODEL
except Exception:
    _MODEL = "llama3.2"


class QueryPlannerAgent(BaseAgent):
    """
    Decomposes a competitor name into 12-14 targeted research sub-questions.
    Uses Ollama to tailor questions to the specific company; falls back to templates.

    Input:  ``{"company_name": "...", "domain": "...", "user_context": {...}}``
    Output: ``{"queries": [{"id": "...", "q": "..."}]}``
    """

    name = "query_planner"
    description = "Decomposes a competitor into targeted research questions (gpt-researcher pattern)."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict")

        company = context.input.get("company_name") or context.input.get("domain", "").split(".")[0]
        if not company:
            return AgentResult.exception(agent=self.name, reason="Missing 'company_name'")

        user_ctx = context.input.get("user_context", {})

        # Always start with deterministic template queries
        queries = [{"id": qid, "q": q.format(c=company)} for qid, q in _TEMPLATES]

        # If Ollama available, add 2-3 context-aware queries tailored to our business
        if _OLLAMA_OK:
            extra = self._llm_context_queries(company, user_ctx)
            queries.extend(extra)
            source = DecisionSource.LLM
        else:
            source = DecisionSource.CODE

        logger.info("query_planner: generated %d queries for '%s'", len(queries), company)
        return AgentResult.passed(agent=self.name, payload={"queries": queries}, source=source)

    def _llm_context_queries(self, company: str, user_ctx: dict) -> list[dict[str, str]]:
        our_biz = user_ctx.get("what_you_do", "")
        diffs = ", ".join(user_ctx.get("differentiators", []))
        prompt = (
            f'Generate 3 highly specific research questions about "{company}" that would help '
            f'a company that "{our_biz}" with differentiators: {diffs} compete against them.\n'
            f'Format: one question per line, no numbering, no explanation.'
        )
        try:
            resp = _ollama.chat(
                model=_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3},
            )
            lines = [l.strip() for l in resp["message"]["content"].strip().splitlines() if l.strip()]
            return [{"id": f"custom_{i}", "q": q} for i, q in enumerate(lines[:3])]
        except Exception as exc:
            logger.debug("query_planner: ollama failed — %s", exc)
            return []
