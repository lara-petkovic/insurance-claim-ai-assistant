from app.agents.technical_agents.shared import *

class ExclusionCheckingAgent(BaseAgent):
    name = "ExclusionCheckingAgent"
    agent_type = "validator"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_text = context.request.claim_description.lower()
        policy_exclusions = context.memory.get("PolicyConceptExtractionAgent", {}).get("exclusions", [])
        targeted_checks = [
            item
            for item in context.memory.get("HomeInsuranceFunctionalAgent", {}).get("checklist", [])
            if isinstance(item, dict) and item.get("target_agent") == self.name
        ]
        found = []
        for exclusion in policy_exclusions:
            concept = exclusion.get("concept")
            if concept == "unoccupied_home" and _contains(claim_text, "unoccupied", "empty", "away for months"):
                found.append({"concept": concept, "severity": "high", "reason": "Claim suggests home may have been unoccupied."})
            if concept == "gradual_damage" and _contains(claim_text, "months", "slow", "gradual", "long time"):
                found.append({"concept": concept, "severity": "high", "reason": "Claim suggests gradual damage."})
            if concept == "rot" and _contains(claim_text, "rot", "mold", "mould"):
                found.append({"concept": concept, "severity": "medium", "reason": "Claim mentions rot or mold."})
            if concept == "poor_maintenance" and _contains(claim_text, "maintenance", "old", "neglected"):
                found.append({"concept": concept, "severity": "medium", "reason": "Claim may involve maintenance condition."})
            if concept == "pipe_or_apparatus_itself" and _contains(claim_text, "replace the pipe", "repair the pipe"):
                found.append({"concept": concept, "severity": "medium", "reason": "Damage to the pipe itself may be excluded."})

        fallback = {"potential_exclusions": found, "targeted_checks": targeted_checks}
        model_client = get_model_client()
        model_result = model_client.json_response(
            system=(
                "You are an insurance exclusion checking agent. "
                "Return only valid JSON. Be conservative: uncertainty should be flagged for human review."
            ),
            prompt=(
                "Check whether policy exclusions may apply to this claim. "
                "Use this JSON shape: {potential_exclusions}. "
                "potential_exclusions must be an array of objects with concept, severity, reason, and evidence_text if available.\n\n"
                f"CLAIM DESCRIPTION:\n{context.request.claim_description}\n\n"
                f"CLAIM FACTS:\n{context.memory.get('ClaimExtractionAgent', {})}\n\n"
                f"POLICY EXCLUSIONS:\n{policy_exclusions}\n\n"
                f"FUNCTIONAL TARGETED CHECKS:\n{targeted_checks}\n\n"
                f"RETRIEVED POLICY EVIDENCE:\n"
                f"{[item.model_dump() for response in context.responses if response.agent_name == 'RetrievalAgent' for item in response.evidence]}"
            ),
            fallback=fallback,
        )
        final_findings = {**fallback, **model_result.data, "model_used": model_result.used_model}
        final_findings["potential_exclusions"] = _as_dict_list(
            final_findings.get("potential_exclusions"),
            default_key="concept",
        )
        found = final_findings.get("potential_exclusions", found)

        return AgentResponse(
            agent_name=self.name,
            findings=final_findings,
            confidence=0.72,
            warnings=(
                ["Used configured model provider for exclusion checking."]
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

class MissingDocumentsAgent(BaseAgent):
    name = "MissingDocumentsAgent"
    agent_type = "validator"

    REQUIREMENTS = {
        "water_damage": ["damage photos", "plumber report", "repair estimate"],
        "storm_damage": ["damage photos", "weather report", "repair estimate"],
        "theft": ["police report", "proof of ownership"],
        "fire_damage": ["damage photos", "incident report", "repair estimate"],
        "broken_glass": ["damage photos", "repair estimate"],
    }

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        provided_names = " ".join(context.request.supporting_document_names).lower()
        targeted_checks = [
            item
            for item in context.memory.get("HomeInsuranceFunctionalAgent", {}).get("checklist", [])
            if isinstance(item, dict) and item.get("target_agent") == self.name
        ]
        missing = []
        for requirement in self.REQUIREMENTS.get(claim_type, ["supporting evidence"]):
            if requirement == "damage photos":
                if not context.request.damage_image_filename:
                    missing.append(requirement)
                continue
            tokens = requirement.split()
            if not any(token in provided_names for token in tokens):
                missing.append(requirement)

        return AgentResponse(
            agent_name=self.name,
            findings={"missing_documents": missing, "targeted_checks": targeted_checks},
            confidence=0.83,
            warnings=[] if not missing else ["Claim package is incomplete."],
            requires_human_review=bool(missing),
            messages=[
                self.message(
                    f"Evidence checklist completed with {len(missing)} missing document(s).",
                    to_agent="OutputValidatorAgent",
                    message_type="validation",
                    metadata={"missing_documents": missing, "targeted_checks": targeted_checks},
                )
            ],
        )

class ConsistencyVerificationAgent(BaseAgent):
    name = "ConsistencyVerificationAgent"
    agent_type = "validator"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        visual = context.memory.get("VisualEvidenceAgent", {})
        detected_damage = visual.get("detected_damage", "unknown")
        issues = []
        if detected_damage != "unknown" and claim_type != "unknown":
            visual_to_claim = {
                "theft_damage": "theft",
                "water_damage": "water_damage",
                "fire_damage": "fire_damage",
                "storm_damage": "storm_damage",
                "broken_glass": "broken_glass",
            }
            expected = visual_to_claim.get(detected_damage, detected_damage)
            if expected != claim_type:
                issues.append(f"Image suggests {detected_damage}, while claim was classified as {claim_type}.")
        if not context.request.incident_date:
            issues.append("Incident date is missing, so policy-period validation cannot be completed.")

        return AgentResponse(
            agent_name=self.name,
            findings={"consistency_issues": issues},
            confidence=0.78 if not issues else 0.5,
            warnings=issues,
            requires_human_review=bool(issues),
            messages=[
                self.message(
                    f"Consistency verification completed with {len(issues)} issue(s).",
                    to_agent="OutputValidatorAgent",
                    message_type="validation",
                    metadata={"consistency_issues": issues},
                )
            ],
        )

class CitationAgent(BaseAgent):
    name = "CitationAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        retrieval_evidence = []
        for response in context.responses:
            if response.agent_name == "RetrievalAgent":
                retrieval_evidence.extend(response.evidence)
        return AgentResponse(
            agent_name=self.name,
            findings={"citation_count": len(retrieval_evidence)},
            evidence=retrieval_evidence[:4],
            confidence=0.84 if retrieval_evidence else 0.25,
            warnings=[] if retrieval_evidence else ["No citations available for final decision."],
            requires_human_review=not bool(retrieval_evidence),
            messages=[
                self.message(
                    f"Attached {len(retrieval_evidence[:4])} citation(s) from retrieved policy evidence.",
                    to_agent="OutputValidatorAgent",
                    message_type="handoff",
                    metadata={"citation_count": len(retrieval_evidence[:4])},
                )
            ],
        )

class OutputValidatorAgent(BaseAgent):
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
        return AgentResponse(
            agent_name=self.name,
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

