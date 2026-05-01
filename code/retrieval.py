"""Stage 4 — BM25 retrieval.

Builds a single in-memory BM25 index over all .md files under a corpus root
(skipping `index.md` per Rev 5 §3 + §7). Tokenizer is unicode-aware
(`re.findall(r"[\\w']+", text.lower())`). File iteration order is `sorted()`
so the index is byte-stable across Windows/Linux/macOS.

Spec: docs/PLAN.md Rev 4 Stage 4, Rev 5 §6 (tokenizer), Rev 5 §7 (sorted
+ index.md filter), Rev 5.1 (no further refinements).
"""
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from . import config

TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """BM25 tokenizer: lowercase + unicode-aware word extraction."""
    return TOKEN_RE.findall(text.lower())


def build_index(corpus_root: Path) -> dict:
    """Build a BM25 index over all .md files under ``corpus_root``,
    EXCLUDING any file named ``index.md``.

    Returns ``{"paths": [Path, ...], "bm25": BM25Okapi}``. Paths are sorted.
    """
    candidates = sorted(
        p
        for p in corpus_root.rglob("*")
        if p.is_file() and p.suffix == ".md" and p.name != "index.md"
    )
    docs: list[list[str]] = []
    valid_paths: list[Path] = []
    for p in candidates:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        docs.append(tokenize(text))
        valid_paths.append(p)
    if not docs:
        # rank_bm25 requires non-empty corpus; return a usable empty index.
        return {"paths": [], "bm25": None}
    bm25 = BM25Okapi(docs, k1=config.BM25_K1, b=config.BM25_B)
    return {"paths": valid_paths, "bm25": bm25}


def retrieve(
    query: str,
    index: dict,
    top_k: int | None = None,
    score_threshold: float | None = None,
) -> list[dict]:
    """Returns up to ``top_k`` hits as
    ``[{"path": str, "score": float, "snippet": str}]``.

    Hits below ``score_threshold`` are filtered. Empty query → empty list.
    """
    top_k = top_k if top_k is not None else config.BM25_TOP_K
    threshold = (
        score_threshold if score_threshold is not None else config.BM25_SCORE_THRESHOLD
    )
    tokens = tokenize(query)
    if not tokens or index.get("bm25") is None:
        return []
    scores = index["bm25"].get_scores(tokens)
    ranked = sorted(
        zip(scores, index["paths"], strict=False),
        key=lambda x: x[0],
        reverse=True,
    )
    hits: list[dict] = []
    for score, path in ranked[:top_k]:
        if score < threshold:
            break
        snippet = path.read_text(encoding="utf-8", errors="replace")[:500]
        hits.append(
            {
                "path": str(path).replace("\\", "/"),
                "score": float(score),
                "snippet": snippet,
            }
        )
    return hits
