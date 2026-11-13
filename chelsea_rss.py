#!/usr/bin/env python3
"""
Chelsea FC News -> Atom feed generator

Source: Chelsea FC's internal news-listing JSON API (found in the page's
inline __webSettings__ / NewsListModule data-props, not publicly documented,
so it may change without notice).

API: https://www.chelseafc.com/en/api/news/listing/7rJyiGvKIDGe6kNF0jRwJ5

IMPORTANT LIMITATIONS (verified against live API response):
- The API returns only: id, title, type, category, url, thumbnail. There is
  NO article body/snippet/description field. <summary> is therefore limited
  to "type / category" - there is no richer content available from this
  endpoint without fetching each article page individually.
- The API returns NO publish-date field. This script derives a best-effort
  <published> date from (in order of preference):
    1. A YYYY/MM/DD date embedded in the thumbnail asset path
       (e.g. ".../editorial/news/2026/08/02/...")
    2. The Cloudinary asset version number in the thumbnail URL
       (e.g. "v1785686546"), which is a Unix timestamp of when the image
       was uploaded - usually same-day as publish, but not guaranteed.
    3. Fallback: current time (script run time), same as <updated>.
  This is NOT a verified article-publish timestamp. Treat it as an estimate.

Usage:
    python3 chelsea_rss.py                 # writes feed.xml (Atom 1.0)
    python3 chelsea_rss.py --out feed.xml
    python3 chelsea_rss.py --limit 30
"""

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import requests

API_URL = "https://www.chelseafc.com/en/api/news/listing/7rJyiGvKIDGe6kNF0jRwJ5"
SITE_BASE = "https://www.chelseafc.com"
FEED_TITLE = "Chelsea FC - Latest News"
FEED_ALT_LINK = "https://www.chelseafc.com/en/news/latest-news"
FEED_SUBTITLE = "Unofficial Atom feed generated from Chelsea FC's news listing API."
FEED_ID = "tag:chelseafc.com,2026:latest-news"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Matches .../2026/08/02/... in an asset path
DATE_PATH_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")
# Matches Cloudinary version prefix like v1785686546
CLOUDINARY_VERSION_RE = re.compile(r"/v(\d{9,13})/")


def fetch_items(limit: int) -> list[dict]:
    """Fetch news items from the Chelsea FC API. Handles a couple of
    plausible JSON shapes since the exact schema wasn't verified live."""
    resp = requests.get(API_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, dict) and "items" in data:
        items = data["items"]
    elif isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "initialContent" in data:
        items = data["initialContent"].get("items", [])
    else:
        raise ValueError(
            "Unrecognized JSON shape from API. Top-level keys: "
            f"{list(data.keys()) if isinstance(data, dict) else type(data)}"
        )

    return items[:limit]


def extract_published(item: dict, now_str: str) -> tuple[str, str]:
    """
    Best-effort published date for an item.
    Returns (rfc3339_string, method) where method is one of:
      "path-date", "cloudinary-version", "fallback-now"
    """
    thumb_id = ""
    thumb_url = ""
    try:
        thumb_id = item["thumbnail"]["id"] or ""
    except (KeyError, TypeError):
        pass
    try:
        thumb_url = item["thumbnail"]["file"]["url"] or ""
    except (KeyError, TypeError):
        pass

    # 1. Date embedded in asset path, e.g. editorial/news/2026/08/02/...
    for source in (thumb_id, thumb_url):
        m = DATE_PATH_RE.search(source)
        if m:
            year, month, day = (int(x) for x in m.groups())
            try:
                dt = datetime(year, month, day, tzinfo=timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "path-date"
            except ValueError:
                pass  # bad date components, fall through

    # 2. Cloudinary version number = unix timestamp of upload
    m = CLOUDINARY_VERSION_RE.search(thumb_url)
    if m:
        try:
            ts = int(m.group(1))
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "cloudinary-version"
        except (ValueError, OSError, OverflowError):
            pass

    # 3. Fallback - same logic as <updated>
    return now_str, "fallback-now"


# ------------------------------------------------------------------ real dates
# The listing API has no publish date, but each article page does: the ArticleHeader component's data-props hold
# articleHeaderDetails.date. Each new article is fetched once and its date kept in a small JSON cache, so a run
# only fetches the handful of new stories. Video pages have no date and keep the estimate.

ARTICLE_DATE_RE = re.compile(r'"articleHeaderDetails":\{.*?"date":"([^"]+)"', re.S)


def article_date(page: str) -> str | None:
    """The article's publish date from its page, as RFC 3339 UTC, or None."""
    m = ARTICLE_DATE_RE.search(html.unescape(page))
    if not m:
        return None
    raw = m.group(1).encode().decode("unicode_escape")  # \u002B is "+"
    raw = re.sub(r"(\.\d+)", lambda f: f.group(1)[:7], raw)  # Python takes up to 6 fraction digits
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=15)
    resp.raise_for_status()
    return resp.text


def _link(item: dict) -> str:
    rel_url = item.get("url", "")
    return rel_url if rel_url.startswith("http") else SITE_BASE + rel_url


def _item_id(item: dict) -> str:
    return item.get("id") or hashlib.sha1(_link(item).encode()).hexdigest()


def resolve_dates(items: list[dict], cache: dict, fetch=fetch_page, max_fetch: int = 40) -> dict:
    """Adds the real date for each item not yet in the cache. A failed fetch is retried next run; a page without a
    date is remembered so it isn't fetched again."""
    fetched = 0
    for item in items:
        item_id = _item_id(item)
        if item_id in cache or fetched >= max_fetch:
            continue
        fetched += 1
        try:
            page = fetch(_link(item))
        except Exception as e:  # network or HTTP error: try again next run
            print(f"WARNING: no page for {_link(item)}: {e}", file=sys.stderr)
            continue
        date = article_date(page)
        cache[item_id] = {"date": date, "source": "article" if date else "none"}
    return cache


def load_dates(path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_dates(path, cache: dict, keep) -> None:
    """Writes the cache, keeping only the items still in the feed."""
    kept = {k: v for k, v in cache.items() if k in set(keep)}
    Path(path).write_text(json.dumps(kept, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def normalise(item: dict, now_str: str, dates: dict | None = None) -> dict:
    """Map a Chelsea API item to standard feed fields."""
    rel_url = item.get("url", "")
    link = rel_url if rel_url.startswith("http") else SITE_BASE + rel_url

    thumb = ""
    try:
        thumb = item["thumbnail"]["file"]["url"]
    except (KeyError, TypeError):
        pass

    category = ""
    try:
        category = item["category"]["title"]
    except (KeyError, TypeError):
        pass

    item_id = item.get("id") or hashlib.sha1(link.encode()).hexdigest()

    known = (dates or {}).get(item_id) or {}
    if known.get("date"):
        published, method = known["date"], "article"
    else:
        published, method = extract_published(item, now_str)

    return {
        "id": item_id,
        "title": item.get("title", "Untitled"),
        "link": link,
        "category": category,
        "type": item.get("type", ""),
        "thumbnail": thumb,
        "published": published,
        "date_method": method,
    }


def build_atom(items: list[dict], self_url: str, dates: dict | None = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    entries = []
    for it in items:
        n = normalise(it, now, dates)
        summary_bits = [n["type"], n["category"], f"date-source:{n['date_method']}"]
        summary = " / ".join(b for b in summary_bits if b)
        thumb_link = (
            f'<link rel="enclosure" type="image/jpeg" href="{escape(n["thumbnail"])}"/>'
            if n["thumbnail"]
            else ""
        )
        entries.append(f"""
  <entry>
    <title>{escape(n['title'])}</title>
    <link rel="alternate" href="{escape(n['link'])}"/>
    {thumb_link}
    <id>tag:chelseafc.com,2026:news:{escape(n['id'])}</id>
    <published>{n['published']}</published>
    <updated>{now}</updated>
    <summary>{escape(summary)}</summary>
  </entry>""")

    self_link = f'<link rel="self" href="{escape(self_url)}"/>' if self_url else ""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{escape(FEED_TITLE)}</title>
  <link rel="alternate" href="{escape(FEED_ALT_LINK)}"/>
  {self_link}
  <id>{escape(FEED_ID)}</id>
  <updated>{now}</updated>
  <subtitle>{escape(FEED_SUBTITLE)}</subtitle>{''.join(entries)}
</feed>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="feed.xml", help="Output file path")
    parser.add_argument("--limit", type=int, default=20, help="Max items in feed")
    parser.add_argument(
        "--self-url",
        default="",
        help="Public URL this feed will be served at (used for the atom:link rel=self tag)",
    )
    parser.add_argument(
        "--dates",
        default="",
        help="JSON cache of real publish dates read from article pages (fetched once per new article)",
    )
    args = parser.parse_args()

    try:
        items = fetch_items(args.limit)
    except Exception as e:
        print(f"ERROR fetching/parsing API: {e}", file=sys.stderr)
        sys.exit(1)

    if not items:
        print("WARNING: no items returned - check API response shape.", file=sys.stderr)

    dates = None
    if args.dates:
        dates = resolve_dates(items, load_dates(args.dates))
        save_dates(args.dates, dates, keep=[_item_id(i) for i in items])

    xml = build_atom(items, args.self_url, dates)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(xml)

    print(f"Wrote {len(items)} items to {args.out}")


if __name__ == "__main__":
    main()
