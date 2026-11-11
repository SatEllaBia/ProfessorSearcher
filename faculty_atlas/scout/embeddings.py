"""Embedding utilities using fastembed (local, no API key required)."""

import json
import os
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

_MODEL_NAME = "BAAI/bge-small-en-v1.5"
# Persist the model in ~/.cache/phd-scout so it survives reboots.
# Override with FASTEMBED_CACHE_PATH if needed.
_CACHE_DIR = os.environ.get(
    "FASTEMBED_CACHE_PATH",
    str(Path.home() / ".cache" / "phd-scout" / "fastembed"),
)
_model = None  # lazy singleton


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(_MODEL_NAME, cache_dir=_CACHE_DIR)
    return _model


def build_professor_text(p: dict) -> str:
    """Build a single text blob from a professor profile dict for embedding.

    Uses summary + keywords + paper titles (no abstracts — too noisy).
    Handles None/missing fields gracefully.
    keywords and recent_papers may be either Python lists or JSON strings.
    """
    parts: list[str] = []

    if p.get("summary"):
        parts.append(p["summary"])

    keywords = p.get("keywords")
    if keywords:
        if isinstance(keywords, list):
            kws = keywords
        else:
            try:
                kws = json.loads(keywords)
                if not isinstance(kws, list):
                    kws = [str(keywords)]
            except (json.JSONDecodeError, TypeError):
                kws = [str(keywords)]
        parts.append(" ".join(str(k) for k in kws))

    papers = p.get("recent_papers")
    if papers:
        if isinstance(papers, list):
            plist = papers
        else:
            try:
                plist = json.loads(papers)
            except (json.JSONDecodeError, TypeError):
                plist = []
        if isinstance(plist, list):
            titles = [
                str(pp["title"])
                for pp in plist
                if isinstance(pp, dict) and pp.get("title")
            ]
            if titles:
                parts.append(". ".join(titles))

    return ". ".join(parts) if parts else ""


def embed_one(text: str) -> NDArray[np.float32]:
    """Embed a single string, return a normalised float32 vector."""
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text")
    model = _get_model()
    vec = np.array(next(model.embed([text])), dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def cosine_similarities(
    query: NDArray[np.float32],
    matrix: NDArray[np.float32],
) -> NDArray[np.float32]:
    """Compute cosine similarity between query and each row of matrix.

    Both query and matrix rows are assumed to be pre-normalised (unit vectors),
    so this reduces to a dot product.
    """
    return matrix @ query
