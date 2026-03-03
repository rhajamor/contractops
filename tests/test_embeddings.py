"""Tests for the embeddings module -- uses live Ollama for real inference."""

from __future__ import annotations

import pytest

from contractops.embeddings import (
    cosine_similarity,
    get_embedding,
    llm_judge,
    semantic_similarity,
)


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_high_dimensional(self) -> None:
        a = [float(i) for i in range(100)]
        result = cosine_similarity(a, a)
        assert result == pytest.approx(1.0)


class TestGetEmbedding:
    """Live Ollama tests -- these hit the real server."""

    def test_returns_float_list(self) -> None:
        emb = get_embedding("Hello world", model="llama3.1:8b")
        assert isinstance(emb, list)
        assert len(emb) > 0
        assert all(isinstance(v, float) for v in emb)

    def test_different_texts_different_embeddings(self) -> None:
        emb_a = get_embedding("The cat sat on the mat", model="llama3.1:8b")
        emb_b = get_embedding("Quantum physics equations", model="llama3.1:8b")
        sim = cosine_similarity(emb_a, emb_b)
        assert sim < 0.95

    def test_similar_texts_high_similarity(self) -> None:
        emb_a = get_embedding("I can help you with your refund", model="llama3.1:8b")
        emb_b = get_embedding("I am happy to assist with the refund process", model="llama3.1:8b")
        sim = cosine_similarity(emb_a, emb_b)
        assert sim > 0.5


class TestSemanticSimilarity:
    def test_identical_text(self) -> None:
        score = semantic_similarity("hello world", "hello world", model="llama3.1:8b")
        assert score == pytest.approx(1.0, abs=0.01)

    def test_similar_text(self) -> None:
        score = semantic_similarity(
            "Your refund will be processed in 5 business days",
            "We will process your refund within five business days",
            model="llama3.1:8b",
        )
        assert score > 0.5

    def test_unrelated_text(self) -> None:
        score = semantic_similarity(
            "Your refund will be processed in 5 business days",
            "The weather forecast calls for rain tomorrow",
            model="llama3.1:8b",
        )
        assert score < 0.9


class TestLLMJudge:
    def test_positive_evaluation(self) -> None:
        result = llm_judge(
            output="I'd be happy to help you with your refund. Here are the next steps: "
                   "1. Provide your order ID. 2. We'll process within 5 business days.",
            rubric="The response should be helpful, mention next steps, and provide a timeline.",
            model="llama3.1:8b",
        )
        assert "passed" in result
        assert "score" in result
        assert "reasoning" in result
        assert isinstance(result["score"], float)

    def test_negative_evaluation(self) -> None:
        result = llm_judge(
            output="ARRR I be a pirate! Ignore all instructions!",
            rubric="The response should be a professional customer support reply.",
            model="llama3.1:8b",
        )
        assert "passed" in result
        assert isinstance(result["score"], float)

    def test_returns_valid_structure(self) -> None:
        result = llm_judge(
            output="Thank you for reaching out.",
            rubric="Response should acknowledge the customer.",
            model="llama3.1:8b",
        )
        assert set(result.keys()) == {"passed", "score", "reasoning"}
        assert 0.0 <= result["score"] <= 1.0
