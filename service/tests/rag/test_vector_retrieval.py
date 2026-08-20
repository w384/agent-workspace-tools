"""Tests for the pure-Python char n-gram vector retrieval scorer."""

from __future__ import annotations

import pytest

from service.app.rag.contracts import Chunk
from service.app.rag.vector_retrieval import (
    CharNgramRetrievalScorer,
    make_retrieval_scorer,
)


def _chunk(*, text: str, chunk_id: str = "c1") -> Chunk:
    return Chunk(
        tenant_id="t1",
        asset_id="a1",
        asset_version_id="v1",
        chunk_id=chunk_id,
        ordinal=0,
        text=text,
        page_number=1,
        paragraph_index=0,
        parser_version="demo",
        embedding_version="char-bigram-v1",
        index_version="demo",
    )


INCOME_CHUNK = _chunk(
    text=(
        "2024年度公司营业收入为 4,860 万元，较上年增长 18%。"
        "主要来源于设备销售与技术服务。纳税申报收入与财务口径一致。"
    ),
    chunk_id="income",
)
BALANCE_CHUNK = _chunk(
    text=(
        "截至2024年末，公司总资产 7,200 万元，其中应收账款 1,480 万元，"
        "存货 1,120 万元；总负债 3,400 万元，资产负债率约 47%。"
    ),
    chunk_id="balance",
)
FLOW_CHUNK = _chunk(
    text=(
        "公司主要结算账户 2024 年度经营性现金流入合计 5,120 万元，"
        "其中销售回款 4,760 万元，与销售收入匹配。"
    ),
    chunk_id="flow",
)


def test_make_retrieval_scorer_returns_callable() -> None:
    scorer = make_retrieval_scorer()
    assert callable(scorer)


def test_identical_text_scores_high() -> None:
    scorer = CharNgramRetrievalScorer()
    same = _chunk(text=INCOME_CHUNK.text)
    score = scorer.score(INCOME_CHUNK.text, same)
    assert score >= 0.99


def test_question_retrieves_topic_chunk_over_unrelated() -> None:
    scorer = CharNgramRetrievalScorer()
    revenue_question = "公司去年的营业收入是多少？"
    revenue_score = scorer.score(revenue_question, INCOME_CHUNK)
    balance_score = scorer.score(revenue_question, BALANCE_CHUNK)
    flow_score = scorer.score(revenue_question, FLOW_CHUNK)
    assert revenue_score > balance_score
    assert revenue_score > flow_score


def test_asset_question_retrieves_balance_chunk() -> None:
    scorer = CharNgramRetrievalScorer()
    balance_question = "公司的应收账款和存货金额是多少？"
    assert scorer.score(balance_question, BALANCE_CHUNK) > scorer.score(
        balance_question, INCOME_CHUNK
    )


def test_unrelated_text_scores_low_or_zero() -> None:
    scorer = CharNgramRetrievalScorer()
    unrelated = _chunk(text="这是一份完全不相关的内容，例如招标公告正文。")
    question = "公司的营业收入是多少？"
    assert scorer.score(question, unrelated) < scorer.score(
        question, INCOME_CHUNK
    )


def test_empty_question_scores_zero() -> None:
    scorer = CharNgramRetrievalScorer()
    assert scorer.score("", INCOME_CHUNK) == 0.0
    assert scorer.score("   ", INCOME_CHUNK) == 0.0


@pytest.mark.parametrize(
    ("question", "expected_chunk"),
    [
        ("销售收入和回款是否匹配", "flow"),
        ("负债情况如何", "balance"),
    ],
)
def test_top_chunk_varies_with_question(
    question: str,
    expected_chunk: str,
) -> None:
    scorer = CharNgramRetrievalScorer()
    chunks = {
        "income": INCOME_CHUNK,
        "balance": BALANCE_CHUNK,
        "flow": FLOW_CHUNK,
    }
    ranked = sorted(
        chunks.items(),
        key=lambda item: scorer.score(question, item[1]),
        reverse=True,
    )
    assert ranked[0][0] == expected_chunk


def test_fullwidth_and_whitespace_are_normalized() -> None:
    scorer = CharNgramRetrievalScorer()
    chunk = _chunk(text="营业收入：４８６０万元")
    question = "营业收入 4860 万元"
    assert scorer.score(question, chunk) > 0.0

