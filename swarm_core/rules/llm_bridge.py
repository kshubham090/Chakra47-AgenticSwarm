from __future__ import annotations

import json
from typing import Any

import ollama

from swarm_core.base import AgentContext, AgentResult, AgentStatus, DecisionSource
from swarm_core.config import OLLAMA_HOST, OLLAMA_MODEL
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_DECISION_MAP: dict[str, AgentStatus] = {
    "BLOCK": AgentStatus.BLOCK,
    "ESCALATE": AgentStatus.ESCALATE,
    "PASS": AgentStatus.PASS,
}

_PROMPT_TEMPLATE = """\
You are a safety gate for an autonomous agent swarm.
Classify the following input as exactly one of: PASS, BLOCK, or ESCALATE.

PASS     — input is safe to proceed.
BLOCK    — input must be denied immediately.
ESCALATE — input requires human review before proceeding.

Input:
{input}

Respond with a JSON object only, no other text:
{{"decision": "<PASS|BLOCK|ESCALATE>", "reason": "<one sentence>"}}"""


_MAX_RETRIES = 3


class LLMBridge:
    """
    Ollama-backed fallback classifier.
    Only invoked by RuleEngine when no symbolic rule matches.
    Always tags results as DecisionSource.LLM.
    Retries up to _MAX_RETRIES times; defaults to ESCALATE (human review)
    rather than stopping the pipeline if all attempts fail.
    """

    def __init__(self, max_retries: int = _MAX_RETRIES) -> None:
        self._client = ollama.Client(host=OLLAMA_HOST)
        self._model = OLLAMA_MODEL
        self._max_retries = max_retries

    def classify(self, context: AgentContext, agent_name: str) -> AgentResult:
        prompt = _PROMPT_TEMPLATE.format(input=str(context.input))
        last_error: str = "unknown error"

        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.chat(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                )
                result = self._parse_response(response["message"]["content"], agent_name)
                if result.status != AgentStatus.EXCEPTION:
                    return result
                # Unrecognized output — log and retry with the same prompt
                last_error = result.reason
                logger.warning(
                    "LLM bridge attempt %d/%d: unrecognized output — retrying. (%s)",
                    attempt, self._max_retries, last_error,
                )
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "LLM bridge attempt %d/%d failed: %s",
                    attempt, self._max_retries, exc,
                )

        # All retries exhausted — ESCALATE for human review instead of stopping the pipeline
        logger.error(
            "LLM bridge exhausted %d retries; defaulting to ESCALATE. Last error: %s",
            self._max_retries, last_error,
        )
        return AgentResult.escalate(
            agent=agent_name,
            reason=f"LLM bridge unavailable after {self._max_retries} attempts — escalated for human review",
            source=DecisionSource.LLM,
        )

    def _parse_response(self, text: str, agent_name: str) -> AgentResult:
        decision: str
        reason: str
        try:
            data: dict[str, Any] = json.loads(text.strip())
            decision = str(data.get("decision", "")).upper()
            reason = str(data.get("reason", "LLM classification"))
        except (json.JSONDecodeError, AttributeError):
            decision = self._extract_keyword(text)
            reason = "LLM classification (unstructured response)"

        status = _DECISION_MAP.get(decision)
        if status is None:
            # Signal to classify() to retry — not a terminal failure yet
            return AgentResult.exception(
                agent=agent_name,
                reason=f"LLM returned unrecognized decision: {text[:200]}",
            )

        src = DecisionSource.LLM
        if status == AgentStatus.BLOCK:
            return AgentResult.blocked(agent=agent_name, reason=reason, source=src)
        if status == AgentStatus.ESCALATE:
            return AgentResult.escalate(agent=agent_name, reason=reason, source=src)
        return AgentResult.passed(agent=agent_name, payload={"llm_reason": reason}, source=src)

    @staticmethod
    def _extract_keyword(text: str) -> str:
        upper = text.upper()
        for keyword in _DECISION_MAP:
            if keyword in upper:
                return keyword
        return ""
