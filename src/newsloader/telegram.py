"""Send the digest to Telegram (D12)."""

import argparse
import html
import json
import os

import httpx

API = "https://api.telegram.org/bot{token}/sendMessage"
LIMIT = 4096


def format_paper(number: int, paper: dict) -> str:
    """Format one paper as an HTML block."""
    title = html.escape(paper["title"])
    summary = html.escape(paper["summary"])
    url = html.escape(paper["url"], quote=True)
    lines = [f'{number}. <a href="{url}">{title}</a>', summary]
    if paper["why"]:
        lines.append(f"💡 {html.escape(paper['why'])}")
    return "\n".join(lines)


def build_messages(papers: list[dict]) -> list[str]:
    """Join formatted papers into messages that each stay under LIMIT."""
    if not papers:
        return ["Quiet day: no papers today."]
    # ponytail: a block is under ~1.5k chars (summary capped by MAX_TOKENS), so one block never hits LIMIT
    messages = []
    message = ""
    for number, paper in enumerate(papers, start=1):
        block = format_paper(number, paper)
        if not message:
            message = block
        elif len(message) + 2 + len(block) > LIMIT:
            messages.append(message)
            message = block
        else:
            message = message + "\n\n" + block
    messages.append(message)
    return messages


def send_message(text: str, token: str, chat_id: str, post=httpx.post) -> None:
    """Post one HTML message; report errors without echoing the token."""
    response = post(
        API.format(token=token),
        timeout=30,
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )
    if response.is_error:  # not raise_for_status: its message would leak the token URL
        raise RuntimeError(f"Telegram error {response.status_code}: {response.text}")


def main(
    fixture_path: str = "tests/fixtures/arxiv_sample.json",
    limit: int = 3,
    send: bool = False,
) -> None:
    """Build messages from the first `limit` fixture papers, then print or send them."""
    with open(fixture_path) as file:
        papers = [
            {**paper, "summary": paper["abstract"][:200], "why": "placeholder reason"}
            for paper in json.load(file)[:limit]
        ]
    messages = build_messages(papers)
    if not send:
        for message in messages:
            print(message)
        print(f"dry run: {len(messages)} message(s), pass --send to send")
        return
    for message in messages:
        send_message(
            message,
            os.environ["TELEGRAM_BOT_TOKEN"],
            os.environ["TELEGRAM_CHAT_ID"],
        )
    print(f"sent {len(messages)} message(s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default="tests/fixtures/arxiv_sample.json")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    main(args.fixture, args.limit, args.send)
