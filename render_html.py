#!/usr/bin/env python3
"""Render the Atom feed as a lo-fi, fast, mobile-friendly HTML page.

The feed drives the page: this reads docs/feed.xml (written by chelsea_rss.py)
and writes docs/index.html. Standard library only, no JavaScript in the output.

Usage:
    python3 render_html.py                       # docs/feed.xml -> docs/index.html
    python3 render_html.py --feed feed.xml --out index.html
"""

import argparse
import xml.etree.ElementTree as ET
from datetime import datetime
from html import escape

NS = {"a": "http://www.w3.org/2005/Atom"}


def _text(el, path: str) -> str:
    found = el.find(path, NS)
    return (found.text or "").strip() if found is not None else ""


def parse_feed(xml: str) -> dict:
    root = ET.fromstring(xml)
    entries = []
    for e in root.findall("a:entry", NS):
        link = ""
        for l in e.findall("a:link", NS):
            if l.get("rel", "alternate") == "alternate":
                link = l.get("href", "")
                break
        entries.append({
            "title": _text(e, "a:title") or "Untitled",
            "link": link,
            "published": _text(e, "a:published") or _text(e, "a:updated"),
        })
    # Keep the feed's own order: it is Chelsea's listing order, and the dates are only estimates.
    return {"title": _text(root, "a:title"), "updated": _text(root, "a:updated"), "entries": entries}


def _parse(ts: str):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _day(ts: str, year: int | None = None) -> str:
    dt = _parse(ts)
    if not dt:
        return ""
    return f"{dt.day} {dt:%b}" if dt.year == year else f"{dt.day} {dt:%b %Y}"


def _stamp(ts: str) -> str:
    dt = _parse(ts)
    return f"Updated {dt.day} {dt:%b %Y, %H:%M} UTC" if dt else ""


CSS = (
    ":root{color-scheme:light dark;--bg:#fff;--fg:#111;--mut:#666;--ln:#0033a0;--rule:#e5e5e5}"
    "@media(prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--mut:#999;--ln:#8fb0ff;--rule:#2a2a2a}}"
    "body{margin:0 auto;max-width:40rem;padding:1rem;background:var(--bg);color:var(--fg);"
    "font:1rem/1.4 system-ui,-apple-system,sans-serif}"
    "h1{font-size:1.15rem;margin:0}header p{margin:.25rem 0 1rem;color:var(--mut);font-size:.85rem}"
    "ol{list-style:none;margin:0;padding:0}li{border-top:1px solid var(--rule);padding:.6rem 0;"
    "display:flex;gap:.75rem}time{flex:0 0 5rem;color:var(--mut);font-size:.85rem;padding-top:.1rem}"
    "a{color:var(--ln);text-decoration:none}a:hover,a:focus{text-decoration:underline}"
    "footer{border-top:1px solid var(--rule);padding-top:.75rem;color:var(--mut);font-size:.8rem}"
)


def render(feed: dict) -> str:
    title = escape(feed.get("title") or "Chelsea FC - Latest News")
    updated = _parse(feed.get("updated", ""))
    year = updated.year if updated else None
    if feed["entries"]:
        items = "\n".join(
            f'<li><time datetime="{escape(e["published"])}">{_day(e["published"], year)}</time>'
            f'<a href="{escape(e["link"])}">{escape(e["title"])}</a></li>'
            for e in feed["entries"]
        )
        body = f"<ol>\n{items}\n</ol>"
    else:
        body = "<p>No news right now. Try again shortly.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="alternate" type="application/atom+xml" title="{title}" href="feed.xml">
<style>{CSS}</style>
</head>
<body>
<header><h1>{title}</h1><p>{_stamp(feed.get("updated", ""))} · <a href="feed.xml">Atom feed</a></p></header>
<main>
{body}
</main>
<footer><p>Unofficial. Links go to chelseafc.com. Dates are estimates from image paths.</p></footer>
</body>
</html>
"""


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--feed", default="docs/feed.xml")
    p.add_argument("--out", default="docs/index.html")
    args = p.parse_args(argv)
    with open(args.feed, encoding="utf-8") as f:
        html = render(parse_feed(f.read()))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
