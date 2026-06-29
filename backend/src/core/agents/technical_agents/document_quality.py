from core.agents.technical_agents.shared import *


class DocumentQualityAgent(BaseAgent):
    """Checks whether extracted policy text looks usable before downstream analysis."""

    name = "DocumentQualityAgent"
    agent_type = "validator"

    def run(self, context: AgentContext) -> AgentResponse:
        policy_text = context.memory.get("DocumentIngestionAgent", {}).get("policy_text", "")
        filename = context.memory.get("DocumentIngestionAgent", {}).get("policy_filename")
        issues = []
        if len(policy_text.strip()) < 500:
            issues.append("Policy text is short; PDF extraction may have missed scanned or tabular content.")
        if filename and str(filename).lower().endswith(".pdf") and "\n" not in policy_text:
            issues.append("PDF text has little structure; layout verification or OCR may be needed.")
        if not any(term in policy_text.lower() for term in ["covered", "not covered", "exclusion", "claim"]):
            issues.append("Core policy wording markers were not found in extracted text.")

        return self.respond(
            findings={
                "document_quality_issues": issues,
                "text_length": len(policy_text),
                "layout_review_recommended": bool(issues),
            },
            confidence=0.86 if not issues else 0.48,
            warnings=issues,
            requires_human_review=bool(issues),
            messages=[
                self.message(
                    f"Document quality check completed with {len(issues)} extraction/layout issue(s).",
                    to_agent="OutputValidatorAgent",
                    message_type="validation",
                    metadata={"issues": issues, "text_length": len(policy_text)},
                )
            ],
        )
