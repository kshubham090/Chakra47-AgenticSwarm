from swarm_core.base import AgentContext, AgentResult, BaseAgent


class MyAgent(BaseAgent):
    name = "my_agent"
    description = "One-line description of what this agent does"

    def run(self, context: AgentContext) -> AgentResult:
        result = self._deterministic_logic(context)
        if result.is_resolved:
            return result

        # Only reaches here if deterministic path could not resolve
        return AgentResult.exception(
            agent=self.name,
            reason=f"Could not classify input: {context.input!r}",
        )

    def _deterministic_logic(self, context: AgentContext) -> AgentResult:
        # TODO: implement code-first decision logic here
        # Return AgentResult.passed(), .blocked(), or .escalate()
        # Return AgentResult.exception() only if truly unresolvable
        return AgentResult.exception(agent=self.name, reason="Not implemented")
