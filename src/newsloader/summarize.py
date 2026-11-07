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
        "You write a daily research digest for one busy reader who scans it on a "
        f"phone. Their interests are: {topics}. "
        "Reply with JSON only, in exactly this shape: "
        '{"answer": "one sentence, at most 15 words, with the main result or claim '
        'in the abstract", '
        '"hook": "one question, at most 12 words, that this answer fully answers"}. '
        "Write the answer first, then build the hook from it. "
        "Style examples from another field, do not reuse their facts or numbers: "
        '{"answer": "Riders avoid gaps: connected lanes drew far more trips.", '
        '"hook": "Why do city bike lanes stay empty?"} '
        '{"answer": "About 90 minutes per shift, even after a long break.", '
        '"hook": "How much sleep do night nurses really lose?"}. '
        "Answer: state the result, never what the paper contains or how it is "
        "organized. Credit a result only to the part the abstract says was tested. "
        "If the authors only argue or propose something, say 'the authors argue' or "
        "similar instead of stating it as fact. "
        "Hook: start with Why, How, What, When, Which or Does, never Can. "
        "Words: a smart reader outside this field must understand every word. Replace "
        "every model, method, dataset or tool name and every acronym with what it "
        "does, such as 'a general image model' instead of its name. Use active voice "
        "and no paper-speak like 'the paper' or 'we propose'. Describe an interest in "
        "plain words, never by its underscore name. "
        "Facts: use a concrete number when the abstract has one. Use only facts "
        "stated in the abstract, with no hype."
    )


def summarize(paper: dict, system: str, chat: Chat) -> tuple[dict, int]:
    """Add hook and answer to a paper; fall back to the abstract if the reply is bad."""
    reply, tokens = chat(system, paper["title"] + "\n\n" + paper["abstract"])
    try:
        data = json.loads(reply)
    except json.JSONDecodeError:
        data = {}
    hook = data.get("hook") if isinstance(data, dict) else None
    answer = data.get("answer") if isinstance(data, dict) else None
    if not (
        isinstance(hook, str)
        and isinstance(answer, str)
        and hook.strip()
        and answer.strip()
    ):
        hook, answer = paper["abstract"][:200], ""
    return {**paper, "hook": hook, "answer": answer}, tokens


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
        print(f"  hook: {result['hook']}")
        print(f"  answer: {result['answer']}")
    print(f"tokens: {tokens}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="config/users/matcry.yaml")
    parser.add_argument("--fixture", default="tests/fixtures/arxiv_sample.json")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    main(args.profile, args.fixture, args.limit)
