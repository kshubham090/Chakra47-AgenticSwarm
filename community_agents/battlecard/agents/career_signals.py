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

_DEPT_KEYWORDS: dict[str, list[str]] = {
    "Engineering": ["engineer", "developer", "devops", "backend", "frontend", "full-stack", "sre", "platform"],
    "Product": ["product manager", "product designer", "ux", "ui designer"],
    "Sales": ["account executive", "sales development", "sdr", "bdr", "sales manager", "revenue"],
    "Marketing": ["marketing", "content", "seo", "demand generation", "growth", "brand"],
    "Customer Success": ["customer success", "account manager", "onboarding", "support engineer"],
    "Data & Analytics": ["data scientist", "data analyst", "machine learning", "ml engineer", "bi analyst"],
    "Finance & Legal": ["finance", "accounting", "legal", "compliance", "counsel"],
    "Operations": ["operations", "hr", "recruiter", "people", "office manager"],
}

_TECH_SIGNALS: list[str] = [
    "python", "golang", "rust", "java", "typescript", "react", "kubernetes",
    "aws", "gcp", "azure", "terraform", "postgres", "mongodb", "kafka",
    "spark", "dbt", "snowflake", "openai", "llm", "pytorch",
]

_GROWTH_SIGNALS = re.compile(
    r"we.re\s+(?:hiring|growing|scaling)|join\s+a\s+(?:fast[- ]growing|rocket\s*ship)|series\s+[a-dA-D]\b|hypergrowth",
    re.I,
)


class CareerSignalsAgent(BaseAgent):
    """
    Analyzes the careers page to infer team size, growth stage, and tech stack.

    Input: ``{"html": "<careers page html>", "base_url": "https://example.com"}``
    """

    name = "career_signals"
    description = "Infers company size, growth phase, and tech needs from public job postings."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict with 'html'")

        html = context.input.get("html") or ""

        if not html:
            return AgentResult.passed(
                agent=self.name,
                payload={
                    "open_roles": _ND,
                    "departments": _ND,
                    "tech_signals": _ND,
                    "size_estimate": _ND,
                    "growth_signal": _ND,
                },
            )

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True).lower()

        role_count = self._count_roles(soup)
        departments = self._extract_departments(text)
        tech = self._extract_tech(text)
        size = self._estimate_size(role_count)
        growth = self._detect_growth(text)

        logger.info("career_signals: %d roles, size=%s, growth=%s", role_count, size, growth)
        return AgentResult.passed(
            agent=self.name,
            payload={
                "open_roles": role_count if role_count else _ND,
                "departments": departments if departments else _ND,
                "tech_signals": tech if tech else _ND,
                "size_estimate": size,
                "growth_signal": growth,
            },
        )

    def _count_roles(self, soup: BeautifulSoup) -> int:
        job_tags = soup.find_all(
            attrs={"class": re.compile(r"job|position|opening|role|listing|vacancy", re.I)}
        )
        if job_tags:
            return len(job_tags)
        # Fallback: count li/article tags that likely contain jobs
        sections = soup.find_all(["li", "article"])
        return sum(
            1 for s in sections
            if re.search(r"\b(engineer|manager|designer|analyst|developer|executive)\b", s.get_text(), re.I)
        )

    def _extract_departments(self, text: str) -> dict[str, int]:
        found: dict[str, int] = {}
        for dept, keywords in _DEPT_KEYWORDS.items():
            count = sum(len(re.findall(rf"\b{re.escape(kw)}\b", text)) for kw in keywords)
            if count:
                found[dept] = count
        return dict(sorted(found.items(), key=lambda x: -x[1]))

    def _extract_tech(self, text: str) -> list[str]:
        return [t for t in _TECH_SIGNALS if re.search(rf"\b{re.escape(t)}\b", text)]

    def _estimate_size(self, roles: int) -> str:
        if not roles:
            return _ND
        if roles < 10:
            return "Small (< 50 employees)"
        if roles < 30:
            return "Mid-size (50–300 employees)"
        if roles < 80:
            return "Scaling (300–1000 employees)"
        return "Enterprise (1000+ employees)"

    def _detect_growth(self, text: str) -> str:
        if _GROWTH_SIGNALS.search(text):
            return "High-growth / actively scaling"
        if re.search(r"\bstable\b|\bestablished\b|\bmature\b", text, re.I):
            return "Established / stable"
        return "Unknown"
