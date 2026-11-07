"""Daily digest: fetch, filter, rank, summarize, send (D2, D12, D14)."""

import glob
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from newsloader.filters import filter_papers
from newsloader.rank import (
    embed_gemini,
    load_cache,
    load_profile,
    rank,
    save_cache,
)
from newsloader.sources import all_categories, fetch_papers
from newsloader.summarize import chat_deepseek, summarize, system_prompt
from newsloader.telegram import build_messages, send_message

USERS = "config/users/*.yaml"
STATE_PATH = ".cache/state.json"
FIRST_RUN_HOURS = 72


def load_since() -> datetime:
    """Start after the last paper we processed, or from the first-run window."""
    path = Path(STATE_PATH)
    if path.exists():
        last = json.loads(path.read_text())["last_published"]
        return datetime.fromisoformat(last) + timedelta(seconds=1)
    # not "last 24 hours": the arXiv API lags by days, so resume from the last paper we processed
    return datetime.now(UTC) - timedelta(hours=FIRST_RUN_HOURS)


def save_last_published(papers: list[dict]) -> None:
    """Record the newest published time, so the next run resumes from it."""
    if not papers:
        return
    path = Path(STATE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    # ponytail: local file; moves to Neon when deployed, since Cloud Run disks are wiped
    path.write_text(json.dumps({"last_published": max(p["published"] for p in papers)}))


def build_digest(papers, profile, cache, embed, chat) -> tuple[list[str], int]:
    """Rank for one profile, summarize its top papers, and build the messages."""
    top, tokens = rank(papers, profile, embed, cache)
    system = system_prompt(profile)
    summarized = []
    for paper in top:
        result, used = summarize(paper, system, chat)
        summarized.append(result)
        tokens += used
    return build_messages(summarized), tokens


def main(limit: int | None = None, dry_run: bool = False) -> None:
    """Fetch new papers, then print or send every user their digest."""
    since = load_since()
    fetched = fetch_papers(all_categories(USERS), since)
    kept, _ = filter_papers(fetched)
    if limit is not None:
        kept = kept[:limit]
    print(f"since {since.isoformat()}: fetched {len(fetched)}, kept {len(kept)}")
    cache = load_cache()
    try:
        for path in sorted(glob.glob(USERS)):
            profile = load_profile(path)
            messages, tokens = build_digest(
                kept, profile, cache, embed_gemini, chat_deepseek
            )
            print(f"{profile['name']}: {len(messages)} message(s), {tokens} tokens")
            if dry_run:
                for message in messages:
                    print(message)
            else:
                for message in messages:
                    send_message(
                        message,
                        os.environ["TELEGRAM_BOT_TOKEN"],
                        os.environ[profile["chat_env"]],
                    )
    finally:
        save_cache(cache)
    # only after every send worked, so a failed run retries the same papers
    if not dry_run and limit is None:
        save_last_published(fetched)
