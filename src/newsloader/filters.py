"""Universal structural filter (stage 0). Relevance is per user and lives in stage 1 (see docs/decisions.md D2)."""

import json
import sys
from collections import Counter


def drop_reason(paper: dict, seen_ids: set[str]) -> str | None:
    """Return the first reason this paper should be dropped, or None to keep it."""
    if paper["id"] in seen_ids:  # already seen this id
        return "duplicate"
    if paper["version"] != "v1":  # only the first version
        return "not v1"
    return None


def filter_papers(papers: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]:
    """Split papers into kept and dropped, tracking ids already seen."""
    seen_ids: set[str] = set()
    kept: list[dict] = []
    dropped: list[tuple[dict, str]] = []
    for paper in papers:
        reason = drop_reason(paper, seen_ids)
        seen_ids.add(paper["id"])  # remember every id, kept or not
        if reason is None:
            kept.append(paper)
        else:
            dropped.append((paper, reason))
    return kept, dropped


def main(path: str = "tests/fixtures/arxiv_sample.json") -> None:
    """Load papers from a JSON file, filter them, and print a short summary."""
    with open(path) as file:
        papers = json.load(file)
    kept, dropped = filter_papers(papers)
    print(f"input: {len(papers)} papers")
    print(f"dropped: {len(dropped)}")
    for reason, count in Counter(reason for _, reason in dropped).most_common():
        print(f"  {reason}: {count}")
    print(f"kept: {len(kept)}")
    for paper in kept[:10]:
        print(f"  [{paper['primary_category']}] {paper['title'][:90]}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
