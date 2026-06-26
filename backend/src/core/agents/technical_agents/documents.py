from core.agents.technical_agents.shared import *

class DocumentIngestionAgent(BaseAgent):
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

class DocumentQualityAgent(BaseAgent):
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

