from datetime import date

from core.agents.base import AgentContext
from core.agents.technical_agents.claim_extraction import ClaimExtractionAgent
from core.agents.technical_agents.policy_concept_extraction import PolicyConceptExtractionAgent
from core.models.analysis import PolicyDocument
from core.models.claim import ClaimRequestData
from models.model_client import ModelResult


class FallbackModelClient:
    def json_response(self, **kwargs):
        return ModelResult(data=kwargs["fallback"], used_model=False)


def test_policy_clause_preserves_page_and_exact_offsets(monkeypatch):
    page_one = "POLICY SCHEDULE\nPolicy period: 2026-01-01 to 2026-12-31."
    page_two = "COVERED EVENTS\nEscape of water from a pipe is covered."
    text = f"{page_one}\n\n{page_two}"
    policy = PolicyDocument(
        document_id="policy-123",
        filename="home-policy.pdf",
        text=text,
        extraction_method="pdf_text_extraction",
        pages=[
            {
                "page_number": 1,
                "text": page_one,
                "char_start": 0,
                "char_end": len(page_one),
                "extraction_method": "pdf_text_extraction",
            },
            {
                "page_number": 2,
                "text": page_two,
                "char_start": len(page_one) + 2,
                "char_end": len(text),
                "extraction_method": "pdf_text_extraction",
            },
        ],
    )
    monkeypatch.setattr(
        "core.agents.technical_agents.policy_concept_extraction.get_model_client",
        lambda: FallbackModelClient(),
    )
    context = AgentContext(
        request=ClaimRequestData(
            claim_description="A pipe burst.",
            policy_document=policy,
        ),
        memory={"DocumentIngestionAgent": {"policy_text": text}},
    )

    response = PolicyConceptExtractionAgent().run(context)
    clause = next(item for item in response.findings["coverage_clauses"] if item.concept == "water_damage")

    assert clause.source_document_id == "policy-123"
    assert clause.source_filename == "home-policy.pdf"
    assert clause.page == 2
    assert clause.section_heading == "COVERED EVENTS"
    assert text[clause.char_start : clause.char_end] == clause.evidence_text
    assert clause.stable_location.startswith("page:2:chars:")
    assert clause.extraction_method == "pdf_text_extraction"
    assert clause.verification_status == "machine_verified"
    assert response.findings["policy_period"]["start"] == date(2026, 1, 1)


def test_claim_extraction_emits_typed_provenanced_facts(monkeypatch):
    monkeypatch.setattr(
        "core.agents.technical_agents.claim_extraction.get_model_client",
        lambda: FallbackModelClient(),
    )
    description = "A pipe burst in my bathroom on 2026-06-15."
    context = AgentContext(request=ClaimRequestData(claim_description=description))

    response = ClaimExtractionAgent().run(context)
    claim_type = next(fact for fact in response.findings["facts"] if fact.fact_type == "claim_type")

    assert claim_type.value == "water_damage"
    assert claim_type.source_document_id == "claim-description"
    assert claim_type.source_filename == "claim_description"
    assert claim_type.evidence_text == description
    assert (claim_type.char_start, claim_type.char_end) == (0, len(description))
    assert claim_type.extraction_method == "rule_extraction"
