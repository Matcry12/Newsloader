"""Paper summaries via DeepSeek (D2, D7)."""

import argparse
import json
import os
from collections.abc import Callable

import httpx

from newsloader.rank import load_profile

MODEL = "deepseek-v4-flash"
URL = "https://api.deepseek.com/chat/completions"
MAX_TOKENS = 200

type Chat = Callable[[str, str], tuple[str, int]]


def chat_deepseek(system: str, user: str) -> tuple[str, int]:
    """Ask DeepSeek for one JSON reply; return (reply text, tokens used)."""
    response = httpx.post(
        URL,
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": MAX_TOKENS,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},  # reasoning would eat MAX_TOKENS
        },
        timeout=60,
    )
    response.raise_for_status()
    body = response.json()
    return body["choices"][0]["message"]["content"], body["usage"]["total_tokens"]


def system_prompt(profile: dict) -> str:
    """Static instructions for the digest writer, listing this reader's interests."""
    topics = ", ".join(topic["name"] for topic in profile["topics"])
    return (
        "You write a daily research digest for one reader whose interests are: "
        f"{topics}. "
        "Reply with JSON only, in exactly this shape: "
        '{"summary": "at most 2 plain sentences on what the paper does and finds", '
        '"why": "1 sentence on why it matters to this reader; '
        'name the matching interest"}. '
        "Use only facts stated in the abstract."
    )


def summarize(paper: dict, system: str, chat: Chat) -> tuple[dict, int]:
    """Add summary and why to a paper; fall back to the abstract if the reply is bad."""
    reply, tokens = chat(system, paper["title"] + "\n\n" + paper["abstract"])
    try:
        data = json.loads(reply)
    except json.JSONDecodeError:
        data = {}
    summary = data.get("summary") if isinstance(data, dict) else None
    why = data.get("why") if isinstance(data, dict) else None
    if not (
        isinstance(summary, str)
        and isinstance(why, str)
        and summary.strip()
        and why.strip()
    ):
        summary, why = paper["abstract"][:200], ""
    return {**paper, "summary": summary, "why": why}, tokens


def main(
    profile_path: str = "config/users/matcry.yaml",
    fixture_path: str = "tests/fixtures/arxiv_sample.json",
    limit: int = 3,
) -> None:
    """Summarize the first `limit` fixture papers and print them with the token total."""
    with open(fixture_path) as file:
        papers = json.load(file)[:limit]
    system = system_prompt(load_profile(profile_path))
    tokens = 0
    for paper in papers:
        result, used = summarize(paper, system, chat_deepseek)
        tokens += used
        print(result["title"][:80])
        print(f"  summary: {result['summary']}")
        print(f"  why: {result['why']}")
    print(f"tokens: {tokens}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="config/users/matcry.yaml")
    parser.add_argument("--fixture", default="tests/fixtures/arxiv_sample.json")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    main(args.profile, args.fixture, args.limit)
