from newsloader.filters import drop_reason, filter_papers


def make_paper(**overrides) -> dict:
    """Return a valid v1 paper that the filter keeps."""
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


def test_valid_paper_is_kept():
    assert drop_reason(make_paper(), set()) is None


def test_duplicate_is_dropped():
    assert drop_reason(make_paper(), {"2601.00001"}) == "duplicate"


def test_not_v1_is_dropped():
    assert drop_reason(make_paper(version="v2"), set()) == "not v1"


def test_filter_papers_splits_kept_and_dropped():
    papers = [make_paper(), make_paper(), make_paper(id="2601.00002", version="v2")]
    kept, dropped = filter_papers(papers)
    assert [p["id"] for p in kept] == ["2601.00001"]
    assert [reason for _, reason in dropped] == ["duplicate", "not v1"]
