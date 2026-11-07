"""Fetch new papers from the arXiv API (D2)."""

import argparse
import glob
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from xml.etree import ElementTree

import httpx

from newsloader.rank import load_profile

API = "https://export.arxiv.org/api/query"
PAGE = 200
MAX_PAPERS = 3000
WAIT = 3  # arXiv asks for 1 request per 3 seconds
NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
HEADERS = {"User-Agent": "newsloader/0.1"}


def parse_feed(xml_text: str) -> list[dict]:
    """Turn an Atom feed into paper dicts."""
    root = ElementTree.fromstring(xml_text)
    papers = []
    for entry in root.findall("a:entry", NS):
        raw_id = entry.find("a:id", NS).text.split("/")[-1]  # 2610.40036v1
        paper_id, version = raw_id.rsplit("v", 1)  # split on the last "v"
        papers.append(
            {
                "id": paper_id,
                "version": "v" + version,
                "title": " ".join(entry.find("a:title", NS).text.split()),
                "abstract": " ".join(entry.find("a:summary", NS).text.split()),
                "primary_category": entry.find("x:primary_category", NS).get("term"),
                "categories": [
                    cat.get("term") for cat in entry.findall("a:category", NS)
                ],
                "published": entry.find("a:published", NS).text,
                "url": f"https://arxiv.org/abs/{raw_id}",
            }
        )
    return papers


def get_page(categories: list[str], start: int, get=httpx.get, sleep=time.sleep) -> str:
    """Fetch one page of the newest submissions in any of the categories."""
    params = {
        "search_query": " OR ".join(f"cat:{cat}" for cat in categories),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "start": start,
        "max_results": PAGE,
    }
    for attempt in range(4):
        response = get(
            API, params=params, headers=HEADERS, timeout=60, follow_redirects=True
        )
        if response.status_code not in (429, 503) or attempt == 3:
            break
        sleep(30)  # rate limited: back off and try again
    response.raise_for_status()
    return response.text


def fetch_papers(
    categories: list[str], since: datetime, get=httpx.get, sleep=time.sleep
) -> list[dict]:
    """Page through the newest submissions, keeping papers published since `since`."""
    kept: list[dict] = []
    for start in range(0, MAX_PAPERS, PAGE):
        if start:
            sleep(WAIT)  # only between requests
        papers = parse_feed(get_page(categories, start, get, sleep))
        if not papers:
            # ponytail: an empty page ends the fetch; arXiv sometimes returns one by
            # mistake, add a retry if counts look short
            break
        kept += [p for p in papers if datetime.fromisoformat(p["published"]) >= since]
        if datetime.fromisoformat(papers[-1]["published"]) < since:
            break  # everything after this paper is older still
    return kept


def all_categories(pattern: str = "config/users/*.yaml") -> list[str]:
    """Sorted union of the categories watched by every profile."""
    categories: set[str] = set()
    for path in glob.glob(pattern):
        categories.update(load_profile(path)["categories"])
    return sorted(categories)


def main(hours: int = 24) -> None:
    """Fetch the last `hours` of papers for every profile and print a summary."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    categories = all_categories()
    print(f"categories: {', '.join(categories)}")
    papers = fetch_papers(categories, since)
    print(f"fetched: {len(papers)} papers in the last {hours} hours")
    for date, count in sorted(Counter(p["published"][:10] for p in papers).items()):
        print(f"  {date}: {count}")
    for paper in papers[:5]:
        print(f"  {paper['title'][:80]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    main(parser.parse_args().hours)
