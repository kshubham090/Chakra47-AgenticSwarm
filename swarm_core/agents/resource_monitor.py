from __future__ import annotations

from typing import Any

import psutil

from swarm_core.base import AgentContext, AgentResult, BaseAgent
from swarm_core.utils import get_logger

logger = get_logger(__name__)

_DEFAULTS: dict[str, float] = {
    "cpu_critical": 95.0,
    "cpu_elevated": 80.0,
    "memory_critical": 90.0,
    "memory_elevated": 75.0,
    "disk_critical": 95.0,
    "disk_elevated": 85.0,
}


class ResourceMonitor(BaseAgent):
    """Monitors CPU, memory, and disk utilization. Always deterministic — no LLM path."""

    name = "resource_monitor"
    description = "Checks system resource utilization against configurable thresholds."

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._cpu_critical: float = cfg.get("cpu_critical", _DEFAULTS["cpu_critical"])
        self._cpu_elevated: float = cfg.get("cpu_elevated", _DEFAULTS["cpu_elevated"])
        self._memory_critical: float = cfg.get("memory_critical", _DEFAULTS["memory_critical"])
        self._memory_elevated: float = cfg.get("memory_elevated", _DEFAULTS["memory_elevated"])
        self._disk_critical: float = cfg.get("disk_critical", _DEFAULTS["disk_critical"])
        self._disk_elevated: float = cfg.get("disk_elevated", _DEFAULTS["disk_elevated"])

    def run(self, context: AgentContext) -> AgentResult:
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        snapshot = self._collect()
        violations = self._check_violations(snapshot)

        critical = [v for v in violations if v["level"] == "critical"]
        if critical:
            summary = ", ".join(f"{v['resource']} {v['value']:.1f}%" for v in critical)
            return AgentResult.blocked(
                agent=self.name, reason=f"Critical resource usage: {summary}"
            )

        if violations:
            summary = ", ".join(f"{v['resource']} {v['value']:.1f}%" for v in violations)
            return AgentResult.escalate(
                agent=self.name, reason=f"Elevated resource usage: {summary}"
            )

        return AgentResult.passed(agent=self.name, payload={"snapshot": snapshot})

    def _collect(self) -> dict[str, float]:
        try:
            disk_pct = psutil.disk_usage("/").percent
        except Exception:
            disk_pct = 0.0
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": disk_pct,
        }

    def _check_violations(self, snapshot: dict[str, float]) -> list[dict[str, Any]]:
        checks = [
            ("cpu_percent", self._cpu_critical, self._cpu_elevated, "CPU"),
            ("memory_percent", self._memory_critical, self._memory_elevated, "Memory"),
            ("disk_percent", self._disk_critical, self._disk_elevated, "Disk"),
        ]
        violations: list[dict[str, Any]] = []
        for key, critical, elevated, label in checks:
            value = snapshot.get(key, 0.0)
            if value >= critical:
                violations.append({"resource": label, "value": value, "level": "critical"})
            elif value >= elevated:
                violations.append({"resource": label, "value": value, "level": "elevated"})
        return violations
