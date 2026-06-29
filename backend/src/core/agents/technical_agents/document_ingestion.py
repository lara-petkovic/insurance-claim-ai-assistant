from core.agents.technical_agents.shared import *


class DocumentIngestionAgent(BaseAgent):
    """Loads extracted policy text and upload metadata into shared agent memory."""

    name = "DocumentIngestionAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        request = context.request
        policy_text = request.policy_text.strip()
        warnings = []
        if not request.policy_text.strip():
            warnings.append("No policy text was provided or extracted. Upload a policy PDF/text file before analysis.")
        findings = {
            "policy_filename": request.policy_filename,
            "policy_text": policy_text,
            "policy_text_length": len(policy_text),
            "supporting_documents": request.supporting_document_names,
            "damage_image_filename": request.damage_image_filename,
        }
        return self.respond(
            findings=findings,
            confidence=0.9 if policy_text else 0.0,
            warnings=warnings,
            requires_human_review=not bool(policy_text),
            messages=[
                self.message(
                    f"Policy document ingested with {len(policy_text)} extracted characters.",
                    to_agent="PolicyConceptExtractionAgent",
                    message_type="handoff",
                    metadata={"policy_filename": request.policy_filename, "policy_text_length": len(policy_text)},
                )
            ],
        )
