from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_ND: dict[str, Any] = {"data": None, "note": "Not enough public data"}

_TRUSTED_BY_RE = re.compile(
    r"trusted\s+by|used\s+by|loved\s+by|powered\s+by|join\s+(?:\d[\d,]+\s+)?(?:companies|teams|businesses)",
    re.I,
)
_TESTIMONIAL_ATTRS = [
    {"class": re.compile(r"testimonial|quote|review", re.I)},
    {"itemprop": "review"},
]
_LOGO_SECTION_ATTRS = [
    {"class": re.compile(r"logos?|clients?|customers?|partners?|brands?", re.I)},
    {"id": re.compile(r"logos?|clients?|customers?|partners?|brands?", re.I)},
]


class ClientEvidenceAgent(BaseAgent):
    """
    Extracts known clients, testimonials, and case study evidence from homepage + customer pages.

    Input: ``{"homepage_html": "...", "customers_html": "...", "case_studies_html": "..."}``
    """

    name = "client_evidence"
    description = "Extracts known clients, testimonials, and case study signals from public pages."

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        if not isinstance(context.input, dict):
            return AgentResult.exception(agent=self.name, reason="Input must be a dict")

        homepage_html = context.input.get("homepage_html") or ""
        customers_html = context.input.get("customers_html") or ""
        case_studies_html = context.input.get("case_studies_html") or ""

        clients: list[str] = []
        testimonials: list[dict[str, str]] = []
        case_study_count = 0

        for html in [homepage_html, customers_html]:
            if html:
                clients += self._extract_logo_names(html)
                testimonials += self._extract_testimonials(html)

        if case_studies_html:
            case_study_count = self._count_case_studies(case_studies_html)
            clients += self._extract_logo_names(case_studies_html)

        clients = list(dict.fromkeys(c for c in clients if len(c) > 1))[:30]
        testimonials = testimonials[:10]

        logger.info(
            "client_evidence: %d clients, %d testimonials, %d case studies",
            len(clients), len(testimonials), case_study_count,
        )
        return AgentResult.passed(
            agent=self.name,
            payload={
                "known_clients": clients if clients else _ND,
                "testimonials": testimonials if testimonials else _ND,
                "case_study_count": case_study_count if case_study_count else _ND,
            },
        )

    def _extract_logo_names(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        names: list[str] = []

        for attrs in _LOGO_SECTION_ATTRS:
            for section in soup.find_all(attrs=attrs):
                for img in section.find_all("img"):
                    alt = img.get("alt", "").strip()
                    title = img.get("title", "").strip()
                    name = alt or title
                    if name and len(name) < 60 and not re.match(r"^(logo|image|img|icon)$", name, re.I):
                        names.append(name)

        return names

    def _extract_testimonials(self, html: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(html, "lxml")
        results: list[dict[str, str]] = []

        for attrs in _TESTIMONIAL_ATTRS:
            for block in soup.find_all(attrs=attrs):
                quote_tag = block.find(["blockquote", "p"])
                quote = quote_tag.get_text(strip=True) if quote_tag else block.get_text(strip=True)
                if len(quote) < 20:
                    continue
                cite = block.find(["cite", "footer", "span"])
                attribution = cite.get_text(strip=True) if cite else ""
                results.append({"quote": quote[:300], "attribution": attribution[:100]})

        return results

    def _count_case_studies(self, html: str) -> int:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.find_all(
            attrs={"class": re.compile(r"case.?stud|customer.?stor|success.?stor|card|article", re.I)}
        )
        return len(cards)
