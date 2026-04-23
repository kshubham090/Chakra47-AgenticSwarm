from swarm_core.audit.chain import AuditChain, AuditEntry
from swarm_core.base import AgentContext, AgentResult, BaseAgent


class AuditAgent(BaseAgent):
    """
    Tamper-evident SHA-256 hash-chain logger.
    NEVER calls LLM — 100% deterministic, always.
    """

    name = "audit_agent"
    description = "Logs every agent decision to a cryptographic hash-chain in Supabase."

    def __init__(self, chain: AuditChain) -> None:
        self._chain = chain

    def run(self, context: AgentContext) -> AgentResult:
        # No exception path exists here — audit is always deterministic
        return self._deterministic_logic(context)

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        result_to_audit: AgentResult | None = context.metadata.get("result_to_audit")
        if result_to_audit is None:
            return AgentResult.blocked(
                agent=self.name,
                reason="AuditAgent requires context.metadata['result_to_audit'] to be set.",
            )

        entry: AuditEntry = self._chain.log(
            task_id=context.task_id,
            agent=result_to_audit.agent,
            status=result_to_audit.status.value,
            decision_source=result_to_audit.decision_source.value,
            raw_input=context.input,
            reason=result_to_audit.reason,
            extra_payload=result_to_audit.payload,
        )

        return AgentResult.passed(
            agent=self.name,
            payload={"block_hash": entry.block_hash, "entry_id": entry.id},
        )
