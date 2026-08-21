from core.models.analysis import PolicyDocument
from core.provenance import policy_clause
from data.retrieval import retrieve_passages, retrieve_policy_clauses, split_passages, tokenize


def test_tokenize_normalizes_words():
    assert tokenize("Water-Damage, WATER.") == ["water", "damage", "water"]


def test_split_passages_preserves_non_empty_content():
    passages = split_passages("First covered event.\n\nSecond exclusion.")

    assert passages
    assert "First covered event" in passages[0]


def test_retrieve_passages_returns_ranked_evidence():
    evidence = retrieve_passages(
        "Escape of water is covered.\n\nGradual leakage is excluded.",
        "water covered",
        top_k=1,
    )

    assert len(evidence) == 1
    assert evidence[0].source == "policy"
    assert "water" in evidence[0].text.lower()


def test_retrieve_passages_preserves_supporting_document_source():
    evidence = retrieve_passages(
        "The plumber confirmed a sudden pipe rupture.",
        "plumber pipe",
        source="supporting:plumber-report.pdf",
    )

    assert evidence
    assert evidence[0].source == "supporting:plumber-report.pdf"


def test_policy_clause_categories_are_retrieved_independently_with_exact_provenance():
    text = "Theft is covered. Theft means forcible removal."
    document = PolicyDocument(filename="policy.txt", text=text)
    coverage = policy_clause(
        document,
        {"concept": "theft", "evidence_text": "Theft is covered.", "polarity": "covered"},
    )
    definition = policy_clause(
        document,
        {"concept": "theft", "evidence_text": "Theft means forcible removal.", "polarity": "neutral"},
        clause_type="definition",
    )

    coverage_results = retrieve_policy_clauses(
        [coverage, definition], "stolen bicycle", clause_type="coverage", claim_type="theft"
    )
    definition_results = retrieve_policy_clauses(
        [coverage, definition], "stolen bicycle", clause_type="definition", claim_type="theft"
    )

    assert [item.policy_clause_id for item in coverage_results] == [coverage.clause_id]
    assert [item.policy_clause_id for item in definition_results] == [definition.clause_id]
    assert definition_results[0].text == definition.evidence_text
    assert definition_results[0].stable_location == definition.stable_location
