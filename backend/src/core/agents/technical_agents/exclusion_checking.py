from core.agents.base import AgentContext, BaseAgent
from core.agents.technical_agents.shared import _contains, _functional_checklist, _merge_dict_lists_by_key
from core.models.agent import AgentResponse
from core.models.analysis import (
    AssessmentProposition,
    ExclusionFindings,
    ExclusionModelOutput,
    PropositionStatus,
    PropositionType,
)
from models.model_client import get_model_client
from security.input_security import UNTRUSTED_INPUT_SYSTEM_RULE, untrusted_block


class ExclusionCheckingAgent(BaseAgent):
    """Checks whether policy exclusions or domain-specific exclusion risks apply."""

    name = "ExclusionCheckingAgent"
    agent_type = "validator"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_text = context.request.claim_description.lower()
        policy_exclusions = context.memory.get("PolicyConceptExtractionAgent", {}).get("exclusions", [])
        typed_exclusions = context.memory.get("PolicyConceptExtractionAgent", {}).get(
            "exclusion_clauses", []
        )
        targeted_checks = [
            item
            for item in _functional_checklist(context)
            if isinstance(item, dict) and item.get("target_agent") == self.name
        ]
        found = []
        for exclusion in policy_exclusions:
            concept = exclusion.get("concept")
            clause_ids = [
                str(clause.get("clause_id"))
                for clause in typed_exclusions
                if clause.get("concept") == concept and clause.get("clause_id")
            ]
            evidence_text = exclusion.get("evidence_text")
            grounding = {"evidence_text": evidence_text, "policy_clause_ids": clause_ids}
            if concept == "unoccupied_home" and _contains(claim_text, "unoccupied", "empty", "away for months"):
                found.append({"concept": concept, "severity": "high", "reason": "Claim suggests home may have been unoccupied.", **grounding})
            if concept == "gradual_damage" and _contains(claim_text, "months", "slow", "gradual", "long time"):
                found.append({"concept": concept, "severity": "high", "reason": "Claim suggests gradual damage.", **grounding})
            if concept == "rot" and _contains(claim_text, "rot", "mold", "mould"):
                found.append({"concept": concept, "severity": "medium", "reason": "Claim mentions rot or mold.", **grounding})
            if concept == "poor_maintenance" and _contains(claim_text, "maintenance", "old", "neglected"):
                found.append({"concept": concept, "severity": "medium", "reason": "Claim may involve maintenance condition.", **grounding})
            if concept == "pipe_or_apparatus_itself" and _contains(claim_text, "replace the pipe", "repair the pipe"):
                found.append({"concept": concept, "severity": "medium", "reason": "Damage to the pipe itself may be excluded.", **grounding})

        fallback = {"potential_exclusions": found, "targeted_checks": targeted_checks}
        model_client = get_model_client()
        model_result = model_client.json_response(
            system=(
                "You are an insurance exclusion checking agent. "
                "Return only valid JSON. Be conservative: uncertainty should be flagged for human review. "
                + UNTRUSTED_INPUT_SYSTEM_RULE
            ),
            prompt=(
                "Check whether policy exclusions may apply to this claim. "
                "Use this JSON shape: {potential_exclusions, suspected_prompt_injection}. "
                "potential_exclusions must be an array of objects with concept, severity, reason, and evidence_text if available.\n\n"
                f"CLAIM DESCRIPTION:\n{untrusted_block('claim_description', context.request.claim_description, max_chars=8000)}\n\n"
                f"CLAIM FACTS:\n{context.memory.get('ClaimExtractionAgent', {})}\n\n"
                f"POLICY EXCLUSIONS:\n{policy_exclusions}\n\n"
                f"FUNCTIONAL TARGETED CHECKS:\n{targeted_checks}\n\n"
                f"RETRIEVED POLICY EVIDENCE:\n"
                f"{[item.model_dump() for response in context.responses if response.agent_name == 'RetrievalAgent' for item in response.evidence if item.source == 'policy']}"
            ),
            fallback=fallback,
            schema_name="exclusion_assessment",
            response_model=ExclusionModelOutput,
            schema_description="Potential policy exclusions with evidence and severity.",
        )
        final_findings = {**fallback, **model_result.data, "model_used": model_result.used_model,
                          "potential_exclusions": _merge_dict_lists_by_key(
                              found,
                              model_result.data.get("potential_exclusions"),
                          )}
        corroborated_concepts = {str(item.get("concept", "")).lower() for item in found}
        for exclusion in final_findings["potential_exclusions"]:
            concept = str(exclusion.get("concept", "")).lower()
            matching_policy_exclusion = next(
                (
                    item for item in policy_exclusions
                    if str(item.get("concept", "")).lower() == concept
                ),
                None,
            )
            if matching_policy_exclusion:
                exclusion["evidence_text"] = matching_policy_exclusion.get("evidence_text")
                exclusion["policy_clause_ids"] = [
                    str(clause.get("clause_id"))
                    for clause in typed_exclusions
                    if str(clause.get("concept", "")).lower() == concept
                    and clause.get("clause_id")
                ]
            if concept not in corroborated_concepts and exclusion.get("severity") == "high":
                exclusion["severity"] = "medium"
                exclusion["requires_corroboration"] = True
        found = final_findings.get("potential_exclusions", found)
        findings = ExclusionFindings.model_validate(final_findings)
        context.propositions = [
            item for item in context.propositions if item.created_by != self.name
        ]
        for index, exclusion in enumerate(found, start=1):
            clause_ids = [str(item) for item in exclusion.get("policy_clause_ids", [])]
            context.propositions.append(
                AssessmentProposition(
                    proposition_id=f"exclusion-{exclusion.get('concept', 'unknown')}-{index}",
                    proposition_type=PropositionType.EXCLUSION,
                    statement=(
                        f"The claim is not barred by the {exclusion.get('concept', 'unknown')} exclusion."
                    ),
                    status=(
                        PropositionStatus.CONTRADICTED
                        if clause_ids else PropositionStatus.INCONCLUSIVE
                    ),
                    required_for_coverage=True,
                    contradicting_policy_clause_ids=clause_ids,
                    confidence=0.85 if clause_ids else 0.3,
                    created_by=self.name,
                )
            )

        return self.respond(
            findings=findings,
            confidence=0.72,
            warnings=(
                ["Used configured model for exclusion checking."]
                if model_result.used_model
                else ([] if not found else ["Potential exclusions require adjuster review."])
            ),
            requires_human_review=bool(found),
            messages=[
                self.message(
                    f"Exclusion review completed with {len(found)} potential exclusion(s).",
                    to_agent="CoverageMatchingAgent",
                    message_type="response",
                    metadata={"potential_exclusions": found, "targeted_checks": targeted_checks},
                )
            ],
        )
