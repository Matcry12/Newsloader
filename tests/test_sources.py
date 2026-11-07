from datetime import UTC, datetime

from newsloader import sources
from newsloader.sources import fetch_papers, get_page, parse_feed

SINCE = datetime(2026, 11, 6, tzinfo=UTC)


class FakeResponse:
    """Minimal httpx.Response stand-in."""

    def __init__(self, text: str = "", status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


def make_entry(
    paper_id: str = "2611.00001",
    version: str = "v1",
    published: str = "2026-11-06T12:00:00Z",
    title: str = "A  study\n of   models",
    categories: tuple[str, ...] = ("cs.CL", "cs.LG"),
) -> str:
    """One Atom entry with a primary category and the given categories."""
    cats = "".join(f'<category term="{cat}" />' for cat in categories)
    return (
        "<entry>"
        f"<id>http://arxiv.org/abs/{paper_id}{version}</id>"
        f"<published>{published}</published>"
        f"<title>{title}</title>"
        "<summary> We study  models.\nSecond line. </summary>"
        f'<arxiv:primary_category term="{categories[0]}" />'
        f"{cats}"
        "</entry>"
    )


def make_feed(*entries: str) -> str:
    """Wrap entries in an Atom feed."""
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom"'
        ' xmlns:arxiv="http://arxiv.org/schemas/atom">'
        f"{''.join(entries)}"
        "</feed>"
    )


def make_get(pages: list[str], calls: list[int]):
    """Fake get: hand out pages in order, recording each requested start."""

    def get(url: str, params: dict, **kwargs) -> FakeResponse:
        calls.append(params["start"])
        return FakeResponse(pages.pop(0))

    return get


def no_sleep(seconds: float) -> None:
    """Record no wait; keep tests instant."""


def test_parse_feed_reads_one_entry():
    papers = parse_feed(make_feed(make_entry(paper_id="2610.40036")))
    assert papers == [
        {
            "id": "2610.40036",
            "version": "v1",
            "title": "A study of models",
            "abstract": "We study models. Second line.",
            "primary_category": "cs.CL",
            "categories": ["cs.CL", "cs.LG"],
            "published": "2026-11-06T12:00:00Z",
            "url": "https://arxiv.org/abs/2610.40036v1",
        }
    ]


def test_fetch_papers_keeps_only_new_papers_and_stops_when_old_reached():
    page = make_feed(
        make_entry(paper_id="2611.00001", published="2026-11-06T12:00:00Z"),
        make_entry(paper_id="2611.00002", published="2026-11-05T12:00:00Z"),
    )
    calls: list[int] = []
    papers = fetch_papers(["cs.CL"], SINCE, get=make_get([page], calls), sleep=no_sleep)
    assert [paper["id"] for paper in papers] == ["2611.00001"]
    assert calls == [0]  # the older last paper ended the fetch


def test_fetch_papers_asks_for_the_next_page(monkeypatch):
    monkeypatch.setattr(sources, "PAGE", 2)
    pages = [
        make_feed(
            make_entry(paper_id="2611.00001"),
            make_entry(paper_id="2611.00002"),
        ),
        make_feed(),
    ]
    calls: list[int] = []
    papers = fetch_papers(["cs.CL"], SINCE, get=make_get(pages, calls), sleep=no_sleep)
    assert [paper["id"] for paper in papers] == ["2611.00001", "2611.00002"]
    assert calls == [0, 2]


def test_get_page_retries_after_a_429():
    sleeps: list[float] = []
    responses = [FakeResponse(status_code=429), FakeResponse(text=make_feed())]

    def get(url: str, params: dict, **kwargs) -> FakeResponse:
        return responses.pop(0)

    text = get_page(["cs.CL", "cs.LG"], 0, get=get, sleep=sleeps.append)
    assert text == make_feed()
    assert sleeps == [30]
