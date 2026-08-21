import re

from core.agents.base import AgentContext, BaseAgent
from core.agents.technical_agents.shared import _functional_checklist
from core.models.agent import AgentResponse
from core.models.analysis import AssessmentProposition, PropositionStatus, PropositionType
from core.provenance import evidence_reference
from security.input_security import detect_prompt_injection


class MissingDocumentsAgent(BaseAgent):
    """Checks whether required claim evidence or supporting documents are missing."""

    name = "MissingDocumentsAgent"
    agent_type = "validator"

    REQUIREMENTS = {
        "water_damage": ["damage photos", "plumber report", "repair estimate"],
        "storm_damage": ["damage photos", "weather report", "repair estimate"],
        "theft": ["police report", "proof of ownership"],
        "fire_damage": ["damage photos", "incident report", "repair estimate"],
        "broken_glass": ["damage photos", "repair estimate"],
        "vehicle_damage": ["damage photos", "repair estimate"],
        "medical": ["medical report", "medical receipts"],
        "baggage_loss": ["carrier or police report", "proof of ownership"],
        "trip_cancellation": ["booking confirmation", "cancellation evidence"],
    }

    ALTERNATIVES = {
        "carrier or police report": [("carrier", "report"), ("police", "report")],
        "supporting evidence": [("evidence",), ("invoice",), ("report",), ("receipt",), ("estimate",)],
    }

    @staticmethod
    def _normalized_words(value: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", value.lower()))

    def _satisfying_document(self, requirement: str, context: AgentContext) -> str | None:
        alternatives = self.ALTERNATIVES.get(requirement, [tuple(requirement.split())])
        for document in context.request.supporting_documents:
            if detect_prompt_injection(document.text):
                continue
            words = self._normalized_words(
                f"{document.filename} {document.document_type} {document.text}"
            )
            if any(all(token in words for token in alternative) for alternative in alternatives):
                return document.filename
        return None

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        targeted_checks = [
            item
            for item in _functional_checklist(context)
            if isinstance(item, dict) and item.get("target_agent") == self.name
        ]
        missing = []
        satisfied_by: dict[str, str] = {}
        for requirement in self.REQUIREMENTS.get(claim_type, ["supporting evidence"]):
            if requirement == "damage photos":
                if not context.request.damage_image_filename:
                    missing.append(requirement)
                continue
            satisfying_document = self._satisfying_document(requirement, context)
            if satisfying_document:
                satisfied_by[requirement] = satisfying_document
            else:
                missing.append(requirement)

        context.propositions = [
            item for item in context.propositions if item.created_by != self.name
        ]
        policy_requirements = context.memory.get("PolicyConceptExtractionAgent", {}).get(
            "condition_clauses", []
        )
        for index, requirement in enumerate(
            self.REQUIREMENTS.get(claim_type, ["supporting evidence"]), start=1
        ):
            clause_ids = self._requirement_clause_ids(requirement, policy_requirements)
            satisfying_filename = satisfied_by.get(requirement)
            proposition_evidence = []
            if satisfying_filename:
                document = next(
                    (
                        item for item in context.request.supporting_documents
                        if item.filename == satisfying_filename
                    ),
                    None,
                )
                if document is not None:
                    reference = evidence_reference(document, document.text.strip())
                    proposition_evidence = [
                        reference.model_copy(update={"source_kind": "supporting_document"})
                    ]
            is_missing = requirement in missing
            context.propositions.append(
                AssessmentProposition(
                    proposition_id=f"missing-evidence-{index}",
                    proposition_type=PropositionType.MISSING_EVIDENCE,
                    statement=(
                        f"Required claim evidence '{requirement}' is missing."
                        if is_missing else
                        f"Required claim evidence '{requirement}' is present."
                    ),
                    status=PropositionStatus.SUPPORTED,
                    required_for_coverage=False,
                    supporting_policy_clause_ids=clause_ids,
                    evidence=proposition_evidence,
                    confidence=0.9 if is_missing or satisfying_filename else 0.7,
                    created_by=self.name,
                )
            )

        return self.respond(
            findings={
                "missing_documents": missing,
                "satisfied_requirements": satisfied_by,
                "targeted_checks": targeted_checks,
            },
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

    @classmethod
    def _requirement_clause_ids(cls, requirement: str, clauses: list) -> list[str]:
        requirement_words = cls._normalized_words(requirement) - {"or", "for", "claim"}
        return [
            str(clause.get("clause_id"))
            for clause in clauses
            if clause.get("clause_id")
            and requirement_words.intersection(cls._normalized_words(str(clause.get("evidence_text", ""))))
        ]
