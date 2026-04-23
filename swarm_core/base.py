from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import uuid


class AgentStatus(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"
    EXCEPTION = "EXCEPTION"


class DecisionSource(str, Enum):
    CODE = "code"
    LLM = "llm"


@dataclass
class AgentContext:
    input: Any
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentResult:
    status: AgentStatus
    agent: str
    decision_source: DecisionSource
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.status in (AgentStatus.PASS, AgentStatus.BLOCK)

    @classmethod
    def passed(
        cls,
        agent: str,
        payload: dict[str, Any] | None = None,
        source: DecisionSource = DecisionSource.CODE,
    ) -> AgentResult:
        return cls(
            status=AgentStatus.PASS,
            agent=agent,
            decision_source=source,
            payload=payload or {},
        )

    @classmethod
    def blocked(
        cls,
        agent: str,
        reason: str,
        source: DecisionSource = DecisionSource.CODE,
    ) -> AgentResult:
        return cls(
            status=AgentStatus.BLOCK,
            agent=agent,
            decision_source=source,
            reason=reason,
        )

    @classmethod
    def escalate(
        cls,
        agent: str,
        reason: str,
        source: DecisionSource = DecisionSource.CODE,
    ) -> AgentResult:
        return cls(
            status=AgentStatus.ESCALATE,
            agent=agent,
            decision_source=source,
            reason=reason,
        )

    @classmethod
    def exception(cls, agent: str, reason: str) -> AgentResult:
        return cls(
            status=AgentStatus.EXCEPTION,
            agent=agent,
            decision_source=DecisionSource.CODE,
            reason=reason,
        )


class BaseAgent(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, context: AgentContext) -> AgentResult:
        """Entry point. Try deterministic path first; raise exception only if unresolved."""
        ...

    @abstractmethod
    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        """Pure code-based decision. Must not call LLM."""
        ...
