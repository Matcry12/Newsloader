import pytest

from newsloader.telegram import LIMIT, build_messages, format_paper, send_message


class FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, status_code: int = 200, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400


def make_paper(**overrides) -> dict:
    """Return a valid summarized paper."""
    paper = {
        "title": "A <b>bold</b> study",
        "summary": "Cats & dogs < 3.",
        "why": "It matches your interest.",
        "url": "https://arxiv.org/abs/2601.00001v1",
    }
    paper.update(overrides)
    return paper


def make_post(response: FakeResponse) -> object:
    """Fake post: returns `response` and records every call."""

    def post(url: str, **kwargs) -> FakeResponse:
        post.calls.append((url, kwargs))
        return response

    post.calls = []
    return post


def test_format_paper_escapes_title_and_summary():
    text = format_paper(1, make_paper())
    assert "<b>" not in text
    assert "&lt;b&gt;" in text
    assert "Cats &amp; dogs &lt; 3." in text
    assert '<a href="https://arxiv.org/abs/2601.00001v1">' in text


def test_format_paper_omits_why_line_when_empty():
    text = format_paper(2, make_paper(why=""))
    assert "💡" not in text
    assert len(text.splitlines()) == 2


def test_build_messages_without_papers_is_a_quiet_day():
    assert build_messages([]) == ["Quiet day: no papers today."]


def test_build_messages_splits_under_limit_and_loses_no_paper():
    papers = [
        make_paper(title=f"Paper number {index}", summary="x" * 1500)
        for index in range(5)
    ]
    messages = build_messages(papers)
    assert len(messages) > 1
    assert all(len(message) <= LIMIT for message in messages)
    for index in range(5):
        assert any(f"Paper number {index}" in message for message in messages)


def test_send_message_posts_html_to_telegram():
    post = make_post(FakeResponse())
    send_message("hi", "SECRET", "42", post=post)
    url, kwargs = post.calls[0]
    assert "SECRET" in url and url.endswith("/sendMessage")
    assert kwargs["json"]["chat_id"] == "42"
    assert kwargs["json"]["text"] == "hi"
    assert kwargs["json"]["parse_mode"] == "HTML"
    assert kwargs["timeout"] == 30


def test_send_message_raises_on_error_without_leaking_token():
    post = make_post(FakeResponse(401, "Unauthorized"))
    with pytest.raises(RuntimeError) as error:
        send_message("hi", "SECRET", "42", post=post)
    assert "401" in str(error.value)
    assert "SECRET" not in str(error.value)
