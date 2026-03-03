"""Embedding-based semantic similarity using Ollama or OpenAI-compatible APIs.

Provides cosine similarity between text pairs using real embedding models,
replacing brittle SequenceMatcher-based string diff with semantic understanding.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

import numpy as np

logger = logging.getLogger("contractops.embeddings")

_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_DEFAULT_EMBED_MODEL = "llama3.1:8b"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)
    dot = float(np.dot(va, vb))
    norm_a = float(np.linalg.norm(va))
    norm_b = float(np.linalg.norm(vb))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_embedding(
    text: str,
    model: str = _DEFAULT_EMBED_MODEL,
    base_url: str = _DEFAULT_OLLAMA_URL,
) -> list[float]:
    """Fetch an embedding vector from the Ollama /api/embed endpoint."""
    payload = {"model": model, "input": text}
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/api/embed",
        data=data,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            embeddings = result.get("embeddings", [])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
            embedding = result.get("embedding", [])
            if embedding:
                return embedding
            raise RuntimeError(f"No embedding returned from {model}")
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Embedding request failed ({base_url}): {exc.reason}"
        ) from exc
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(
            f"Embedding request failed ({base_url}): {exc.code} {body}"
        ) from exc


def semantic_similarity(
    text_a: str,
    text_b: str,
    model: str = _DEFAULT_EMBED_MODEL,
    base_url: str = _DEFAULT_OLLAMA_URL,
) -> float:
    """Compute cosine similarity between two texts using embedding vectors."""
    emb_a = get_embedding(text_a, model=model, base_url=base_url)
    emb_b = get_embedding(text_b, model=model, base_url=base_url)
    return round(cosine_similarity(emb_a, emb_b), 6)


def llm_judge(
    output: str,
    rubric: str,
    model: str = _DEFAULT_EMBED_MODEL,
    base_url: str = _DEFAULT_OLLAMA_URL,
    temperature: float = 0.1,
) -> dict[str, Any]:
    """Use an LLM to evaluate output against a rubric.

    Returns {"passed": bool, "score": float, "reasoning": str}.
    """
    prompt = (
        "You are an evaluation judge. Score the following output against the rubric.\n\n"
        f"RUBRIC:\n{rubric}\n\n"
        f"OUTPUT:\n{output}\n\n"
        "Respond with ONLY a JSON object with these exact keys:\n"
        '- "passed": true or false (does the output satisfy the rubric?)\n'
        '- "score": a number from 0.0 to 1.0\n'
        '- "reasoning": a one-sentence explanation\n\n'
        "JSON response:"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 4096},
        "format": "json",
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/api/chat",
        data=data,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
            content = result.get("message", {}).get("content", "")
            return _parse_judge_response(content)
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        logger.error("LLM judge request failed: %s", exc)
        return {"passed": False, "score": 0.0, "reasoning": f"Judge request failed: {exc}"}


def _parse_judge_response(content: str) -> dict[str, Any]:
    """Parse the JSON response from the LLM judge, with fallback."""
    try:
        parsed = json.loads(content)
        return {
            "passed": bool(parsed.get("passed", False)),
            "score": float(parsed.get("score", 0.0)),
            "reasoning": str(parsed.get("reasoning", "")),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        lower = content.lower()
        passed = "true" in lower or "pass" in lower
        return {
            "passed": passed,
            "score": 1.0 if passed else 0.0,
            "reasoning": content[:200],
        }
