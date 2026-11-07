from datetime import UTC, datetime, timedelta

from newsloader import digest


def make_paper(**overrides) -> dict:
    """Return a valid v1 paper."""
    paper = {
        "id": "2601.00001",
        "version": "v1",
        "title": "A study of agent tool use",
        "abstract": "We study agents that call tools.",
        "primary_category": "cs.CL",
        "categories": ["cs.CL"],
        "published": "2026-01-01T00:00:00Z",
        "url": "https://arxiv.org/abs/2601.00001v1",
    }
    paper.update(overrides)
    return paper


def make_profile() -> dict:
    """Return a one-topic profile."""
    return {
        "name": "tester",
        "chat_env": "TELEGRAM_CHAT_ID",
        "categories": ["cs.CL"],
        "topics": [
            {
                "name": "llm_agents_tool_use",
                "pseudo_abstract": "We study agents that call tools.",
            }
        ],
    }


def make_embed() -> object:
    """Fake embed: one token per text; records every call."""

    def embed(texts: list[str]) -> tuple[list[list[float]], int]:
        embed.calls.append(list(texts))
        return [[float(len(text)), 1.0] for text in texts], len(texts)

    embed.calls = []
    return embed


def make_chat() -> object:
    """Fake chat: always 7 tokens; records every call."""

    def chat(system: str, user: str) -> tuple[str, int]:
        chat.calls.append((system, user))
        return '{"summary": "The fake summary.", "why": "Names the topic."}', 7

    chat.calls = []
    return chat


def test_build_digest_summarizes_top_paper_and_counts_tokens():
    papers = [make_paper()]
    messages, tokens = digest.build_digest(
        papers, make_profile(), {}, make_embed(), make_chat()
    )
    assert len(messages) == 1
    assert papers[0]["title"] in messages[0]
    assert "The fake summary." in messages[0]
    assert tokens == 1 + 1 + 7  # one topic, one paper, one summary


def test_build_digest_with_no_papers_says_quiet_day():
    messages, _ = digest.build_digest([], make_profile(), {}, make_embed(), make_chat())
    assert messages == ["Quiet day: no papers today."]


def test_save_last_published_then_load_since_returns_max_plus_one_second(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(digest, "STATE_PATH", str(tmp_path / "state.json"))
    papers = [
        make_paper(id="a", published="2026-01-01T00:00:00Z"),
        make_paper(id="b", published="2026-01-03T00:00:00Z"),
    ]
    digest.save_last_published(papers)
    assert digest.load_since() == datetime(2026, 1, 3, 0, 0, tzinfo=UTC) + timedelta(
        seconds=1
    )


def test_load_since_without_state_is_first_run_window(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "STATE_PATH", str(tmp_path / "state.json"))
    expected = datetime.now(UTC) - timedelta(hours=digest.FIRST_RUN_HOURS)
    assert abs(digest.load_since() - expected) < timedelta(seconds=60)


def test_save_last_published_without_papers_writes_no_file(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    monkeypatch.setattr(digest, "STATE_PATH", str(path))
    digest.save_last_published([])
    assert not path.exists()
