"""Stage 4 BM25 retrieval tests. Spec: docs/PLAN.md Rev 4 Stage 4 +
Rev 5 §6 (tokenizer) + Rev 5 §7 (sorted paths + index.md filter)."""
from pathlib import Path

import pytest

from code.retrieval import build_index, retrieve, tokenize

FIX_CORPUS = Path(__file__).parent.parent / "fixtures" / "corpus"


@pytest.fixture(scope="module")
def index():
    return build_index(FIX_CORPUS)


def test_tokenizer_unicode():
    tokens = tokenize("ma carte Visa, les règles internes")
    assert "carte" in tokens
    assert "règles" in tokens
    assert "internes" in tokens


def test_tokenizer_lowercases():
    tokens = tokenize("Hello World")
    assert tokens == ["hello", "world"]


def test_index_excludes_index_md(index):
    """Per Rev 5 §3 + §7: index.md files MUST NOT appear in the corpus."""
    paths = [str(p).replace("\\", "/") for p in index["paths"]]
    assert not any(p.endswith("/index.md") for p in paths), paths


def test_index_paths_are_sorted(index):
    """Per Rev 5 §7: file iteration order must be deterministic via sorted()."""
    paths = [str(p) for p in index["paths"]]
    assert paths == sorted(paths)


def test_retrieve_top_hit_for_screen_query(index):
    hits = retrieve("screen test failing", index, top_k=3, score_threshold=0.5)
    assert len(hits) >= 1
    assert "screen-test" in hits[0]["path"]


def test_retrieve_top_hit_for_billing_query(index):
    hits = retrieve("dispute a charge refund", index, top_k=3, score_threshold=0.5)
    assert len(hits) >= 1
    assert "billing-faq" in hits[0]["path"]


def test_retrieve_top_hit_for_vuln_query(index):
    hits = retrieve("security vulnerability", index, top_k=3, score_threshold=0.5)
    assert len(hits) >= 1
    assert "bug-bounty" in hits[0]["path"]


def test_retrieve_top_hit_for_travelers_cheques(index):
    hits = retrieve(
        "travellers cheques lost stolen traveling", index, top_k=3,
        score_threshold=0.5,
    )
    assert len(hits) >= 1
    assert "travelers-cheques" in hits[0]["path"]


def test_retrieve_empty_query_returns_empty(index):
    assert retrieve("", index, top_k=3) == []


def test_retrieve_below_threshold_returns_empty(index):
    """Very high threshold filters everything."""
    hits = retrieve("anything", index, top_k=3, score_threshold=999.0)
    assert hits == []


def test_retrieve_index_md_never_in_results(index):
    """Sanity: even with a query that name-drops every index.md keyword,
    no index.md path should appear (it was filtered at build time)."""
    hits = retrieve(
        "TOC screen billing bug-bounty travelers-cheques visa-rules",
        index, top_k=10, score_threshold=0.0,
    )
    paths = [h["path"] for h in hits]
    assert not any(p.endswith("/index.md") for p in paths), paths
