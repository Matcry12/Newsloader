"""Embedding ranking (stage 1). Embed once, score each user by max cosine over topics (D2, D3, D6)."""

import argparse
import json
import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import yaml

from newsloader.filters import filter_papers

MODEL = "models/gemini-embedding-001"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/{MODEL}:batchEmbedContents"
)
DIMS = 768
CACHE_PATH = ".cache/embeddings.json"
BATCH = 80  # 100 papers measured ~28k tokens; free tier allows 30k a minute
MAX_NEW_PAPERS = (
    900  # free tier allows 1,000 texts a day; leaves room for topics and reruns
)

type Embed = Callable[[list[str]], tuple[list[list[float]], int]]


def load_profile(path: str) -> dict:
    """Load a user profile: name, categories, topics, optional blocked_words."""
    with open(path) as file:
        return yaml.safe_load(file)


def paper_text(paper: dict) -> str:
    """Text we embed for a paper."""
    return paper["title"] + "\n" + paper["abstract"]


def embed_gemini(texts: list[str]) -> tuple[list[list[float]], int]:
    """Embed texts via Gemini in one request; return vectors in order and estimated tokens.

    Callers pass at most BATCH texts.
    """
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
    requests = [
        {
            "model": MODEL,
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": DIMS,
        }
        for text in texts
    ]
    for attempt in range(3):
        response = httpx.post(
            GEMINI_URL, json={"requests": requests}, headers=headers, timeout=60
        )
        if response.status_code != 429 or attempt == 2:
            break
        time.sleep(60)  # free tier limit is per minute
    response.raise_for_status()
    vectors = [item["values"] for item in response.json()["embeddings"]]
    # ponytail: chars/4 estimate, use usage data if D11 needs exact cost
    return vectors, sum(len(text) for text in texts) // 4


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two same-length vectors."""
    norm = sum(x * x for x in a) ** 0.5 * sum(y * y for y in b) ** 0.5
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm


def is_blocked(paper: dict, blocked_words: list[str]) -> bool:
    """True if any blocked word appears in the lowered title or abstract."""
    text = paper_text(paper).lower()
    return any(word.lower() in text for word in blocked_words)


def embed_papers(
    papers: list[dict], embed: Embed, cache: dict[str, list[float]]
) -> int:
    """Embed only papers missing from the cache, BATCH at a time; return tokens used.

    Stops at MAX_NEW_PAPERS to stay inside the free daily quota. Vectors are
    cached per batch, so a failure in a later batch keeps earlier ones.
    """
    new = [paper for paper in papers if paper["id"] not in cache]
    if len(new) > MAX_NEW_PAPERS:
        print(f"warning: free-tier cap, skipping {len(new) - MAX_NEW_PAPERS} papers")
        new = new[:MAX_NEW_PAPERS]
    tokens = 0
    for start in range(0, len(new), BATCH):
        batch = new[start : start + BATCH]
        vectors, batch_tokens = embed([paper_text(paper) for paper in batch])
        for paper, vector in zip(batch, vectors, strict=True):
            cache[paper["id"]] = vector
        tokens += batch_tokens
    return tokens


def score_papers(
    papers: list[dict],
    cache: dict[str, list[float]],
    topic_vecs: dict[str, list[float]],
) -> list[dict]:
    """Score each paper by its best-matching topic; sorted by score descending."""
    results = []
    for paper in papers:
        scores = {
            name: cosine(cache[paper["id"]], vec) for name, vec in topic_vecs.items()
        }
        topic = max(scores, key=scores.get)
        results.append(
            {
                "id": paper["id"],
                "title": paper["title"],
                "score": scores[topic],
                "topic": topic,
            }
        )
    return sorted(results, key=lambda result: result["score"], reverse=True)


def rank(
    papers: list[dict],
    profile: dict,
    embed: Embed,
    cache: dict[str, list[float]],
    k: int = 5,
) -> tuple[list[dict], int]:
    """Drop blocked papers, embed topics and unseen papers, then keep the top k."""
    papers = [
        paper
        for paper in papers
        if not is_blocked(paper, profile.get("blocked_words", []))
    ]
    topics = profile["topics"]
    vectors, tokens = embed([topic["pseudo_abstract"] for topic in topics])
    topic_vecs = {
        topic["name"]: vec for topic, vec in zip(topics, vectors, strict=True)
    }
    tokens += embed_papers(papers, embed, cache)
    embedded = [paper for paper in papers if paper["id"] in cache]
    return score_papers(embedded, cache, topic_vecs)[:k], tokens


def load_cache() -> dict[str, list[float]]:
    """Read the embedding cache, or start empty."""
    path = Path(CACHE_PATH)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_cache(cache: dict[str, list[float]]) -> None:
    """Write the embedding cache, creating .cache if needed."""
    path = Path(CACHE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache))


def main(
    profile_path: str = "config/users/matcry.yaml",
    fixture_path: str = "tests/fixtures/arxiv_sample.json",
    limit: int | None = None,
    k: int = 5,
) -> None:
    """Rank fixture papers for one profile and print the top k."""
    with open(fixture_path) as file:
        papers = json.load(file)
    kept, _ = filter_papers(papers)
    papers = kept[:limit] if limit is not None else kept
    print(f"input: {len(papers)} papers")
    cache = load_cache()
    try:
        results, tokens = rank(
            papers, load_profile(profile_path), embed_gemini, cache, k
        )
    finally:
        save_cache(cache)
    print(f"tokens: {tokens}")
    print(f"top {len(results)}:")
    for result in results:
        print(f"  {result['score']:.3f}  [{result['topic']}] {result['title'][:80]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="config/users/matcry.yaml")
    parser.add_argument("--fixture", default="tests/fixtures/arxiv_sample.json")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    main(args.profile, args.fixture, args.limit, args.k)
