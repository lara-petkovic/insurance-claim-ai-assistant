from data.retrieval import retrieve_passages, split_passages, tokenize


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
