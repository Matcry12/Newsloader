from newsloader.summarize import summarize, system_prompt


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


def make_chat(reply: str) -> object:
    """Fake chat: always returns `reply` and 7 tokens; records every call."""

    def chat(system: str, user: str) -> tuple[str, int]:
        chat.calls.append((system, user))
        return reply, 7

    chat.calls = []
    return chat


def test_summarize_keeps_paper_keys_and_sets_summary_and_why():
    paper = make_paper()
    chat = make_chat('{"summary": "It studies LMs.", "why": "Names rag_retrieval."}')
    result, tokens = summarize(paper, "sys", chat)
    assert result["summary"] == "It studies LMs."
    assert result["why"] == "Names rag_retrieval."
    assert result["id"] == paper["id"]
    assert result["title"] == paper["title"]
    assert tokens == 7
    assert chat.calls == [("sys", paper["title"] + "\n\n" + paper["abstract"])]


def test_summarize_falls_back_on_invalid_json():
    paper = make_paper()
    result, tokens = summarize(paper, "sys", make_chat("not json at all"))
    assert result["summary"] == paper["abstract"][:200]
    assert result["why"] == ""
    assert tokens == 7


def test_summarize_falls_back_when_why_is_missing():
    paper = make_paper()
    reply = '{"summary": "It studies LMs."}'
    result, tokens = summarize(paper, "sys", make_chat(reply))
    assert result["summary"] == paper["abstract"][:200]
    assert result["why"] == ""
    assert tokens == 7


def test_summarize_falls_back_when_reply_is_a_list():
    paper = make_paper()
    result, tokens = summarize(paper, "sys", make_chat('["summary", "why"]'))
    assert result["summary"] == paper["abstract"][:200]
    assert result["why"] == ""
    assert tokens == 7


def test_system_prompt_names_every_topic():
    profile = {"topics": [{"name": "llm_agents_tool_use"}, {"name": "rag_retrieval"}]}
    prompt = system_prompt(profile)
    assert "llm_agents_tool_use" in prompt
    assert "rag_retrieval" in prompt
