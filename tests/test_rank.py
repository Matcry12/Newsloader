import pytest

from newsloader import rank as rank_module
from newsloader.rank import (
    cosine,
    embed_papers,
    is_blocked,
    rank,
    score_papers,
)


def make_paper(**overrides) -> dict:
    """Return a valid v1 paper."""
    paper = {
        "id": "2601.00001",
        "version": "v1",
        "title": "A study of language models",
        "abstract": "We study language models on text.",
        "primary_category": "cs.CL",
        "categories": ["cs.CL"],
        "published": "2026-01-01T00:00:00Z",
        "url": "https://arxiv.org/abs/2601.00001v1",
    }
    paper.update(overrides)
    return paper


def make_embed() -> object:
    """Keyword fake: [agent hits, retrieval hits, 1.0]; records every call."""

    def embed(texts: list[str]) -> tuple[list[list[float]], int]:
        embed.calls.append(list(texts))
        vectors = [
            [text.lower().count("agent"), text.lower().count("retrieval"), 1.0]
            for text in texts
        ]
        return vectors, len(texts)

    embed.calls = []
    return embed


def test_cosine_of_identical_vectors_is_one():
    assert cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_of_orthogonal_vectors_is_zero():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_score_papers_picks_best_topic_and_sorts():
    papers = [make_paper(id="a"), make_paper(id="b")]
    cache = {"a": [0.6, 0.8, 0.0], "b": [1.0, 0.0, 0.0]}
    topic_vecs = {"agents": [1.0, 0.0, 0.0], "rag": [0.0, 1.0, 0.0]}
    results = score_papers(papers, cache, topic_vecs)
    assert [result["id"] for result in results] == ["b", "a"]
    assert [result["topic"] for result in results] == ["agents", "rag"]
    assert results[0]["score"] == pytest.approx(1.0)
    assert results[1]["score"] == pytest.approx(0.8)


def test_is_blocked_is_case_insensitive():
    paper = make_paper(title="Diffusion models for images")
    assert is_blocked(paper, ["diffusion"])
    assert not is_blocked(paper, ["retrieval"])


def test_embed_papers_skips_cached_ids():
    papers = [make_paper(id="a"), make_paper(id="b")]
    cache = {"a": [1.0, 1.0, 1.0]}
    embed = make_embed()
    embed_papers(papers, embed, cache)
    assert embed.calls == [[papers[1]["title"] + "\n" + papers[1]["abstract"]]]
    assert cache["b"] == [0, 0, 1.0]


def test_embed_papers_makes_no_call_when_all_cached():
    papers = [make_paper(id="a")]
    cache = {"a": [1.0, 1.0, 1.0]}
    embed = make_embed()
    assert embed_papers(papers, embed, cache) == 0
    assert embed.calls == []


def test_rank_returns_at_most_k_results():
    papers = [make_paper(id=f"2601.0000{i}") for i in range(5)]
    profile = {
        "topics": [
            {"name": "agents", "pseudo_abstract": "agent"},
            {"name": "rag", "pseudo_abstract": "retrieval"},
        ]
    }
    results, tokens = rank(papers, profile, make_embed(), {}, k=2)
    assert len(results) == 2
    assert tokens == 7  # 2 topic vectors + 5 papers


def make_profile() -> dict:
    """Profile with two topics."""
    return {
        "topics": [
            {"name": "agents", "pseudo_abstract": "agent"},
            {"name": "rag", "pseudo_abstract": "retrieval"},
        ]
    }


def test_embed_papers_stops_at_max_new_papers(monkeypatch):
    monkeypatch.setattr(rank_module, "MAX_NEW_PAPERS", 3)
    papers = [make_paper(id=f"2601.0000{i}") for i in range(5)]
    cache = {}
    embed = make_embed()
    tokens = embed_papers(papers, embed, cache)
    assert len(cache) == 3
    assert sum(len(call) for call in embed.calls) == 3
    assert tokens == 3


def test_embed_papers_calls_embed_once_per_batch(monkeypatch):
    monkeypatch.setattr(rank_module, "BATCH", 2)
    papers = [make_paper(id=f"2601.0000{i}") for i in range(5)]
    cache = {}
    embed = make_embed()
    tokens = embed_papers(papers, embed, cache)
    assert [len(call) for call in embed.calls] == [2, 2, 1]
    assert tokens == 5
    assert len(cache) == 5


def test_embed_papers_keeps_earlier_batches_when_a_later_one_fails(monkeypatch):
    monkeypatch.setattr(rank_module, "BATCH", 2)
    papers = [make_paper(id=f"2601.0000{i}") for i in range(4)]
    cache = {}

    def embed(texts: list[str]) -> tuple[list[list[float]], int]:
        if not cache:
            return [[0.0, 0.0, 1.0] for _ in texts], len(texts)
        raise RuntimeError("quota exceeded")

    with pytest.raises(RuntimeError):
        embed_papers(papers, embed, cache)
    assert list(cache) == [papers[0]["id"], papers[1]["id"]]


def test_rank_scores_only_papers_that_got_embedded(monkeypatch):
    monkeypatch.setattr(rank_module, "MAX_NEW_PAPERS", 3)
    papers = [make_paper(id=f"2601.0000{i}") for i in range(5)]
    results, _ = rank(papers, make_profile(), make_embed(), {}, k=5)
    assert [result["id"] for result in results] == [paper["id"] for paper in papers[:3]]
