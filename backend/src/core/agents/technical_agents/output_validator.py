from core.agents.base import AgentContext, BaseAgent
from core.models.agent import AgentResponse
from core.agents.technical_agents.policy_polarity import exact_text_in_source


class OutputValidatorAgent(BaseAgent):
    """Validates the full agent output and emits feedback for repair or human review."""

    name = "OutputValidatorAgent"
    agent_type = "validator"

    def run(self, context: AgentContext) -> AgentResponse:
        required = [
            "ClaimExtractionAgent",
            "PolicyConceptExtractionAgent",
            "CoverageMatchingAgent",
            "ExclusionCheckingAgent",
            "MissingDocumentsAgent",
        ]
        missing = [name for name in required if name not in context.memory]
        required_model_agents = [
            "ClaimExtractionAgent",
            "PolicyConceptExtractionAgent",
            "CoverageMatchingAgent",
            "ExclusionCheckingAgent",
        ]
        if context.request.damage_image_bytes:
            required_model_agents.extend(["VisualEvidenceAgent", "ImageAuthenticityAgent"])
        non_model_agents = [
            name
            for name in required_model_agents
            if context.memory.get(name, {}).get("model_used") is not True
        ]
        feedback = []
        coverage = context.memory.get("CoverageMatchingAgent", {})
        exclusions = context.memory.get("ExclusionCheckingAgent", {}).get("potential_exclusions", [])
        missing_docs = context.memory.get("MissingDocumentsAgent", {}).get("missing_documents", [])
        consistency = context.memory.get("ConsistencyVerificationAgent", {}).get("consistency_issues", [])
        supporting_extraction_problems = context.memory.get("DocumentIngestionAgent", {}).get(
            "documents_with_extraction_problems", 0
        )
        model_injection_flags = [
            name for name, findings in context.memory.items()
            if findings.get("suspected_prompt_injection") is True
        ]
        citation_evidence = [
            item
            for response in context.responses
            if response.agent_name == "CitationAgent"
            for item in response.evidence
            if item.source == "policy"
        ]
        supporting_passages = coverage.get("supporting_policy_passages", [])
        has_supporting_citation = any(
            exact_text_in_source(passage, item.text) or exact_text_in_source(item.text, str(passage))
            for passage in supporting_passages
            for item in citation_evidence
        )
        if coverage.get("coverage_assessment") == "covered" and not has_supporting_citation:
            feedback.append(
                {
                    "target_agent": "CoverageMatchingAgent",
                    "issue": "Coverage was marked covered but no relevant supporting policy citation is available.",
                    "suggested_action": "Re-run retrieval or downgrade to human review until the exact supporting passage is found.",
                }
            )
        if exclusions:
            feedback.append(
                {
                    "target_agent": "CoverageMatchingAgent",
                    "issue": "Potential exclusions were detected after coverage matching.",
                    "suggested_action": "Final recommendation must mention exclusion risk and require adjuster review.",
                }
            )
        if missing_docs:
            feedback.append(
                {
                    "target_agent": "MissingDocumentsAgent",
                    "issue": "Required claim evidence is missing.",
                    "suggested_action": "Keep final result in human review until documents are provided.",
                }
            )
        if consistency:
            feedback.append(
                {
                    "target_agent": "ConsistencyVerificationAgent",
                    "issue": "Cross-check found inconsistent or incomplete claim facts.",
                    "suggested_action": "Highlight consistency issue in final reasoning.",
                }
            )
        if supporting_extraction_problems:
            feedback.append(
                {
                    "target_agent": "DocumentIngestionAgent",
                    "issue": "One or more supporting documents could not be reliably extracted.",
                    "suggested_action": "Treat facts from unreadable documents as unconfirmed and require human review.",
                }
            )
        if context.request.security_flags or model_injection_flags:
            feedback.append(
                {
                    "target_agent": "OrchestratorAgent",
                    "issue": "Potential prompt injection was detected in untrusted claim evidence.",
                    "suggested_action": "Do not automate the outcome; require human review of original evidence.",
                }
            )
        warnings = []
        if missing:
            warnings.append(f"Missing agent outputs: {', '.join(missing)}")
        if non_model_agents:
            warnings.append(f"These model-backed agents did not use a model: {', '.join(non_model_agents)}")
        if feedback:
            warnings.append("Validator feedback requires final synthesis to preserve human-review context.")
        return self.respond(
            findings={
                "schema_ready": not missing and not non_model_agents,
                "missing_agent_outputs": missing,
                "model_required": True,
                "non_model_agents": non_model_agents,
                "feedback": feedback,
                "security_flags": context.request.security_flags,
                "model_injection_flags": model_injection_flags,
            },
            confidence=1.0 if not missing and not non_model_agents else 0.2,
            warnings=warnings,
            requires_human_review=bool(missing or feedback or non_model_agents),
            messages=[
                self.message(
                    f"Output validation completed with {len(feedback)} feedback item(s).",
                    to_agent="OrchestratorAgent",
                    message_type="feedback",
                    metadata={"feedback": feedback, "missing_agent_outputs": missing, "non_model_agents": non_model_agents},
                )
            ],
        )
