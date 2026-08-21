from core.agents.base import AgentContext, BaseAgent
from core.models.agent import AgentResponse


class DocumentIngestionAgent(BaseAgent):
    """Loads extracted policy text and upload metadata into shared agent memory."""

    name = "DocumentIngestionAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        request = context.request
        policy_text = request.policy_text.strip()
        warnings = list(request.policy_extraction_warnings)
        if not request.policy_text.strip():
            warnings.append("No policy text was provided or extracted. Upload a policy PDF/text file before analysis.")
        supporting_documents = [document.model_dump(mode="json") for document in request.supporting_documents]
        problem_documents = [document for document in request.supporting_documents if document.extraction_warnings or not document.text.strip()]
        for document in problem_documents:
            if document.extraction_warnings:
                warnings.extend(f"{document.filename}: {warning}" for warning in document.extraction_warnings)
            elif not document.text.strip():
                warnings.append(f"{document.filename}: no usable text was extracted.")
        successful_documents = [document for document in request.supporting_documents if document.text.strip()]
        findings = {
            "policy_filename": request.policy_filename,
            "policy_text": policy_text,
            "policy_document": request.policy_document,
            "policy_text_length": len(policy_text),
            "policy_extraction_warnings": warnings,
            "supporting_documents": supporting_documents,
            "supporting_document_count": len(request.supporting_documents),
            "successfully_extracted_document_count": len(successful_documents),
            "documents_with_extraction_problems": len(problem_documents),
            "damage_image_filename": request.damage_image_filename,
        }
        return self.respond(
            findings=findings,
            confidence=0.9 if policy_text else 0.0,
            warnings=warnings,
            requires_human_review=not bool(policy_text) or bool(problem_documents),
            messages=[
                self.message(
                    f"Policy document ingested with {len(policy_text)} extracted characters.",
                    to_agent="PolicyConceptExtractionAgent",
                    message_type="handoff",
                    metadata={"policy_filename": request.policy_filename, "policy_text_length": len(policy_text)},
                )
            ],
        )
