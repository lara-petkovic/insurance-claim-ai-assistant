from core.agents.base import AgentContext
from core.agents.orchestrator import OrchestratorAgent
from core.agents.technical_agents.coverage_matching import CoverageMatchingAgent
from core.agents.technical_agents.output_validator import OutputValidatorAgent
from core.models.agent import AgentResponse, EvidenceItem
from core.models.claim import ClaimRequestData
from models.model_client import ModelClient, ModelResult


def disable_model_calls(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)
    monkeypatch.delenv("OPENAI_PLANNING_MODEL", raising=False)

    from config import get_settings
    from models.model_client import get_model_client

    get_settings.cache_clear()
    get_model_client.cache_clear()
    monkeypatch.setattr(
        ModelClient,
        "_fallback_or_raise",
        lambda self, fallback, error: ModelResult(data=fallback, used_model=False, error=error),
    )


def analyze_theft(monkeypatch, policy_text):
    disable_model_calls(monkeypatch)
    return OrchestratorAgent().analyze(
        ClaimRequestData(
            insurance_type="home",
            claim_description="My bicycle was stolen from the insured home.",
            policy_text=policy_text,
        )
    )


def test_exact_positive_policy_clause_can_support_covered_assessment(monkeypatch):
    policy = "Theft is covered under this policy."

    result = analyze_theft(monkeypatch, policy)

    assert result.coverage_assessment == "covered"
    coverage = next(item for item in result.agent_trace if item.agent_name == "CoverageMatchingAgent")
    assert coverage.findings["clause_polarities"] == ["covered"]
    assert coverage.findings["supporting_policy_passages"] == [policy]
    assert any(item.source == "policy" and policy in item.text for item in result.evidence)


def test_explicit_not_covered_wording_never_becomes_covered(monkeypatch):
    result = analyze_theft(monkeypatch, "Theft is not covered under this policy.")

    assert result.coverage_assessment == "not_covered"
    assert result.claim_status == "likely_not_covered"
    coverage = next(item for item in result.agent_trace if item.agent_name == "CoverageMatchingAgent")
    assert coverage.findings["clause_polarities"] == ["excluded"]
    assert coverage.findings["supporting_policy_passages"] == []


def test_ambiguous_topic_mention_fails_closed_when_model_is_unavailable(monkeypatch):
    result = analyze_theft(monkeypatch, "The policy contains information about theft coverage in an endorsement.")

    assert result.coverage_assessment == "unclear"
    assert result.claim_status == "requires_human_review"


def test_conditional_wording_requires_human_review(monkeypatch):
    result = analyze_theft(monkeypatch, "Theft may be covered if the security conditions are satisfied.")

    assert result.coverage_assessment == "possibly_covered"
    assert result.claim_status == "requires_human_review"


def test_conflicting_policy_clauses_require_human_review(monkeypatch):
    result = analyze_theft(
        monkeypatch,
        "Theft is covered under this policy. Theft is not covered when the bicycle is outdoors.",
    )

    assert result.coverage_assessment == "unclear"
    assert result.claim_status == "requires_human_review"
    coverage = next(item for item in result.agent_trace if item.agent_name == "CoverageMatchingAgent")
    assert coverage.findings["clause_polarities"] == ["covered", "excluded"]


def test_rule_match_does_not_override_contradictory_model_result(monkeypatch):
    class FakeModelClient:
        def json_response(self, **kwargs):
            return ModelResult(
                data={
                    "coverage_assessment": "not_covered",
                    "matched_policy_concepts": [],
                    "explanation": "The model found no applicable cover.",
                },
                used_model=True,
            )

    policy = "Theft is covered under this policy."
    retrieval = AgentResponse(
        agent_name="RetrievalAgent",
        evidence=[EvidenceItem(source="policy", text=policy)],
    )
    context = AgentContext(
        request=ClaimRequestData(claim_description="My bicycle was stolen.", policy_text=policy),
        responses=[retrieval],
        memory={
            "ClaimExtractionAgent": {"claim_type": "theft"},
            "PolicyConceptExtractionAgent": {
                "coverage_clauses": [
                    {
                        "concept": "theft",
                        "polarity": "covered",
                        "evidence_text": policy,
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(
        "core.agents.technical_agents.coverage_matching.get_model_client",
        lambda: FakeModelClient(),
    )

    response = CoverageMatchingAgent().run(context)

    assert response.findings["coverage_assessment"] == "not_covered"


def test_irrelevant_policy_citation_does_not_validate_covered_result():
    policy = "Theft is covered under this policy. Fire claims require photographs."
    citation = AgentResponse(
        agent_name="CitationAgent",
        findings={"citation_count": 1, "policy_citation_count": 1},
        evidence=[EvidenceItem(source="policy", text="Fire claims require photographs.")],
    )
    context = AgentContext(
        request=ClaimRequestData(claim_description="My bicycle was stolen.", policy_text=policy),
        responses=[citation],
        memory={
            "ClaimExtractionAgent": {"model_used": True},
            "PolicyConceptExtractionAgent": {"model_used": True},
            "CoverageMatchingAgent": {
                "coverage_assessment": "covered",
                "supporting_policy_passages": ["Theft is covered under this policy."],
                "model_used": True,
            },
            "ExclusionCheckingAgent": {"potential_exclusions": [], "model_used": True},
            "MissingDocumentsAgent": {"missing_documents": []},
            "CitationAgent": citation.findings,
        },
    )
    response = OutputValidatorAgent().run(context)

    assert response.requires_human_review is True
    assert any("no relevant supporting policy citation" in item["issue"] for item in response.findings["feedback"])
