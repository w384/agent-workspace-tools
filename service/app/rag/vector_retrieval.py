"""Pure-Python character n-gram vector retrieval scorer for the demo.

The demo search replica previously scored every chunk as 1.0 (all hits),
so answers never varied with the question. This module provides a
deterministic, dependency-free, Chinese-aware relevance scorer: text is
tokenized into character bigrams and scored with cosine similarity, so a
question retrieves the document chunks that actually discuss the asked
topic. The scorer is a plug-in for InMemorySearchIndex; the retrieval
gate, evidence threshold and citation binding are unchanged.

No external models are required (pure stdlib), which keeps the demo
runnable offline. An embedding-backed scorer can replace it later via
the same Callable[[str, Chunk], float] contract.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable
from typing import Final

from service.app.rag.contracts import Chunk

_WHITESPACE: Final[re.Pattern[str]] = re.compile(r"\s+")
_NGRAM_N: Final[int] = 2


def _normalize(text: str) -> str:
    """Lowercase, fold full-width forms, drop all whitespace."""
    return _WHITESPACE.sub("", unicodedata.normalize("NFKC", text).lower())


def _char_ngrams(text: str, n: int = _NGRAM_N) -> Counter[str]:
    normalized = _normalize(text)
    if len(normalized) < n:
        # For very short inputs fall back to the whole string as one token.
        return Counter([normalized]) if normalized else Counter()
    return Counter(
        normalized[index : index + n]
        for index in range(len(normalized) - n + 1)
    )


def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(
        count * right.get(gram, 0)
        for gram, count in left.items()
    )
    if dot <= 0:
        return 0.0
    norm_left = math.sqrt(sum(count * count for count in left.values()))
    norm_right = math.sqrt(sum(count * count for count in right.values()))
    if norm_left <= 0 or norm_right <= 0:
        return 0.0
    return dot / (norm_left * norm_right)


class CharNgramRetrievalScorer:
    """Score a question against a chunk with char-bigram cosine similarity.

    The returned score is in [0, 1]; identical normalized text scores 1.0,
    unrelated text scores 0.0. Relevance ordering is preserved under the
    demo evidence threshold because related chunks share far more bigrams.
    """

    def __init__(self, *, n: int = _NGRAM_N) -> None:
        self._n = n

    def score(self, question: str, chunk: Chunk) -> float:
        question_grams = _char_ngrams(question, self._n)
        chunk_grams = _char_ngrams(chunk.text, self._n)
        return _cosine_similarity(question_grams, chunk_grams)


def make_retrieval_scorer() -> Callable[[str, Chunk], float]:
    """Build a deterministic pure-Python vector retrieval scorer."""
    return CharNgramRetrievalScorer().score

