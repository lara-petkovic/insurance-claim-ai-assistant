from core.agents.base import AgentContext, BaseAgent
from core.models.agent import AgentResponse
from models.model_client import get_model_client


class OutputValidatorAgent(BaseAgent):
    """Validates the full agent output and emits feedback for repair or human review."""

    name = "OutputValidatorAgent"
    agent_type = "validator"

    def run(self, context: AgentContext) -> AgentResponse:
        model_client = get_model_client()
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
        citations = context.memory.get("CitationAgent", {})
        exclusions = context.memory.get("ExclusionCheckingAgent", {}).get("potential_exclusions", [])
        missing_docs = context.memory.get("MissingDocumentsAgent", {}).get("missing_documents", [])
        consistency = context.memory.get("ConsistencyVerificationAgent", {}).get("consistency_issues", [])
        if coverage.get("coverage_assessment") == "covered" and not citations.get("citation_count"):
            feedback.append(
                {
                    "target_agent": "CoverageMatchingAgent",
                    "issue": "Coverage was marked covered but no citation is available.",
                    "suggested_action": "Re-run retrieval or downgrade to human review until supporting evidence is found.",
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
        warnings = []
        if missing:
            warnings.append(f"Missing agent outputs: {', '.join(missing)}")
        if model_client.require_models and non_model_agents:
            warnings.append(f"These model-backed agents did not use a model: {', '.join(non_model_agents)}")
        if feedback:
            warnings.append("Validator feedback requires final synthesis to preserve human-review context.")
        return self.respond(
            findings={
                "schema_ready": not missing and not (model_client.require_models and non_model_agents),
                "missing_agent_outputs": missing,
                "model_required": model_client.require_models,
                "non_model_agents": non_model_agents,
                "feedback": feedback,
            },
            confidence=1.0 if not missing and not non_model_agents else 0.2,
            warnings=warnings,
            requires_human_review=bool(missing or feedback or (model_client.require_models and non_model_agents)),
            messages=[
                self.message(
                    f"Output validation completed with {len(feedback)} feedback item(s).",
                    to_agent="OrchestratorAgent",
                    message_type="feedback",
                    metadata={"feedback": feedback, "missing_agent_outputs": missing, "non_model_agents": non_model_agents},
                )
            ],
        )
