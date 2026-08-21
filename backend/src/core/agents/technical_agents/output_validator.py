from __future__ import annotations

from core.agents.base import AgentContext, BaseAgent
from core.models.agent import AgentResponse
from core.models.analysis import PolicyClause, PropositionStatus, PropositionType
from security.input_security import detect_prompt_injection


class OutputValidatorAgent(BaseAgent):
    """Validates conclusion-specific grounding and emits repair or review feedback."""

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
        feedback: list[dict[str, str]] = []
        coverage = context.memory.get("CoverageMatchingAgent", {})
        exclusions = context.memory.get("ExclusionCheckingAgent", {}).get("potential_exclusions", [])
        missing_docs = context.memory.get("MissingDocumentsAgent", {}).get("missing_documents", [])
        consistency = context.memory.get("ConsistencyVerificationAgent", {}).get(
            "consistency_issues", []
        )
        supporting_extraction_problems = context.memory.get("DocumentIngestionAgent", {}).get(
            "documents_with_extraction_problems", 0
        )
        supporting_injection_flags = [
            f"supporting_document:{document.filename}"
            for document in context.request.supporting_documents
            if detect_prompt_injection(document.text)
        ]
        model_injection_flags = [
            name for name, findings in context.memory.items()
            if findings.get("suspected_prompt_injection") is True
        ]

        clauses = self._policy_clauses(context)
        proposition_validation = {
            proposition.proposition_id: self._validate_proposition(proposition, clauses)
            for proposition in context.propositions
        }
        for proposition in context.propositions:
            validation = proposition_validation[proposition.proposition_id]
            if not validation["valid"]:
                feedback.append(
                    {
                        "target_agent": proposition.created_by,
                        "issue": (
                            f"Proposition {proposition.proposition_id} is not grounded: "
                            f"{'; '.join(validation['issues'])}."
                        ),
                        "suggested_action": (
                            "Retrieve and cite the exact corresponding policy clause, or keep the conclusion in human review."
                        ),
                    }
                )
            if proposition.status in {
                PropositionStatus.PROPOSED,
                PropositionStatus.INCONCLUSIVE,
                PropositionStatus.CONTRADICTED,
            }:
                feedback.append(
                    {
                        "target_agent": proposition.created_by,
                        "issue": (
                            f"Proposition {proposition.proposition_id} is {proposition.status.value}."
                        ),
                        "suggested_action": "Resolve the proposition with claim facts and policy clauses or require human review.",
                    }
                )

        coverage_propositions = [
            proposition
            for proposition in context.propositions
            if proposition.proposition_type is PropositionType.COVERAGE
        ]
        required_propositions = [
            proposition for proposition in context.propositions if proposition.required_for_coverage
        ]
        coverage_gate_passed = bool(coverage_propositions) and bool(required_propositions) and all(
            proposition.status is PropositionStatus.SUPPORTED
            and not self._unresolved_contradictions(proposition)
            and proposition_validation[proposition.proposition_id]["valid"]
            for proposition in required_propositions
        )
        requested_covered = coverage.get("coverage_assessment") == "covered"
        if requested_covered and not coverage_gate_passed:
            feedback.append(
                {
                    "target_agent": "CoverageMatchingAgent",
                    "issue": (
                        "Coverage was marked covered but no relevant supporting policy citation is available "
                        "for every required proposition, or an unresolved contradiction remains."
                    ),
                    "suggested_action": (
                        "Re-run proposition-specific retrieval or downgrade to human review until every required conclusion is grounded."
                    ),
                }
            )
            coverage.coverage_assessment = "unclear"

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
        if context.request.security_flags or model_injection_flags or supporting_injection_flags:
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
                "supporting_document_injection_flags": supporting_injection_flags,
                "proposition_validation": proposition_validation,
                "coverage_gate_passed": coverage_gate_passed,
                "validated_coverage_assessment": coverage.get("coverage_assessment", "unclear"),
            },
            confidence=1.0 if not missing and not non_model_agents else 0.2,
            warnings=warnings,
            requires_human_review=bool(missing or feedback or non_model_agents),
            messages=[
                self.message(
                    f"Output validation completed with {len(feedback)} feedback item(s).",
                    to_agent="OrchestratorAgent",
                    message_type="feedback",
                    metadata={
                        "feedback": feedback,
                        "missing_agent_outputs": missing,
                        "non_model_agents": non_model_agents,
                    },
                )
            ],
        )

    @staticmethod
    def _policy_clauses(context: AgentContext) -> dict[str, PolicyClause]:
        findings = context.memory.get("PolicyConceptExtractionAgent", {})
        raw_clauses = findings.get("policy_clauses") or [
            *findings.get("coverage_clauses", []),
            *findings.get("exclusion_clauses", []),
            *findings.get("condition_clauses", []),
            *findings.get("limit_clauses", []),
            *findings.get("definition_clauses", []),
        ]
        clauses = {}
        for item in raw_clauses:
            try:
                clause = item if isinstance(item, PolicyClause) else PolicyClause.model_validate(item)
            except (TypeError, ValueError):
                continue
            clauses[clause.clause_id] = clause
        return clauses

    @classmethod
    def _validate_proposition(cls, proposition, clauses: dict[str, PolicyClause]) -> dict:
        issues: list[str] = []
        referenced_ids = set(
            proposition.supporting_policy_clause_ids + proposition.contradicting_policy_clause_ids
        )
        policy_proposition_types = {
            PropositionType.COVERAGE,
            PropositionType.EXCLUSION,
            PropositionType.CONDITION,
            PropositionType.DEFINITION,
            PropositionType.LIMIT,
        }
        if proposition.proposition_type in policy_proposition_types and not referenced_ids:
            issues.append("the policy conclusion references no policy clause IDs")
        unknown_ids = sorted(referenced_ids - clauses.keys())
        if unknown_ids:
            issues.append(f"unknown policy clause IDs: {', '.join(unknown_ids)}")
        cited_ids: set[str] = set()
        for evidence in proposition.evidence:
            if evidence.source_kind != "policy":
                if proposition.proposition_type in {
                    PropositionType.COVERAGE,
                    PropositionType.EXCLUSION,
                    PropositionType.CONDITION,
                    PropositionType.DEFINITION,
                    PropositionType.LIMIT,
                }:
                    issues.append("a non-policy document was used to ground a policy conclusion")
                continue
            if not evidence.policy_clause_id:
                issues.append("a policy citation has no clause ID")
                continue
            clause = clauses.get(evidence.policy_clause_id)
            if clause is None:
                issues.append(f"citation references unknown clause {evidence.policy_clause_id}")
                continue
            cited_ids.add(clause.clause_id)
            if clause.clause_id not in referenced_ids:
                issues.append(f"citation {clause.clause_id} does not belong to this proposition")
            if not cls._citation_equals_clause(evidence, clause):
                issues.append(f"citation {clause.clause_id} does not exactly match its policy clause")
            if not cls._clause_type_corresponds(proposition.proposition_type, clause, proposition):
                issues.append(f"citation {clause.clause_id} does not correspond to the proposition type")
        if referenced_ids and not cited_ids.intersection(referenced_ids):
            issues.append("no exact cited passage corresponds to the proposition")
        if (
            proposition.status is PropositionStatus.SUPPORTED
            and proposition.supporting_policy_clause_ids
            and not cited_ids.intersection(proposition.supporting_policy_clause_ids)
        ):
            issues.append("no supporting policy clause is cited for the supported proposition")
        missing_contradiction_citations = sorted(
            set(proposition.contradicting_policy_clause_ids) - cited_ids
        )
        if missing_contradiction_citations:
            issues.append(
                "contradicting policy clauses are not cited: "
                f"{', '.join(missing_contradiction_citations)}"
            )
        unresolved = cls._unresolved_contradictions(proposition)
        if unresolved:
            issues.append(f"unresolved contradicting clauses: {', '.join(unresolved)}")
        return {"valid": not issues, "issues": issues, "cited_policy_clause_ids": sorted(cited_ids)}

    @staticmethod
    def _citation_equals_clause(evidence, clause: PolicyClause) -> bool:
        return all(
            getattr(evidence, field) == getattr(clause, field)
            for field in (
                "source_document_id",
                "source_filename",
                "page",
                "section_heading",
                "evidence_text",
                "char_start",
                "char_end",
                "stable_location",
            )
        )

    @staticmethod
    def _clause_type_corresponds(proposition_type, clause: PolicyClause, proposition) -> bool:
        if clause.clause_id in proposition.contradicting_policy_clause_ids:
            return clause.clause_type.value in {"exclusion", "condition"}
        allowed = {
            PropositionType.COVERAGE: {"coverage"},
            PropositionType.EXCLUSION: {"exclusion"},
            PropositionType.CONDITION: {"condition", "requirement"},
            PropositionType.DEFINITION: {"definition"},
            PropositionType.LIMIT: {"limit"},
            PropositionType.MISSING_EVIDENCE: {"condition", "requirement"},
            PropositionType.CLAIM_FACT: set(),
        }
        return clause.clause_type.value in allowed[proposition_type]

    @staticmethod
    def _unresolved_contradictions(proposition) -> list[str]:
        resolved = set(proposition.resolved_policy_clause_ids)
        return [
            clause_id
            for clause_id in proposition.contradicting_policy_clause_ids
            if clause_id not in resolved
        ]
