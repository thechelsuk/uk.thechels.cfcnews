from pathlib import Path

import render_html

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Chelsea FC - Latest News</title>
  <updated>2026-11-13T17:35:47Z</updated>
  <entry>
    <title>Older &amp; wiser</title>
    <link rel="alternate" href="https://www.chelseafc.com/en/news/article/older"/>
    <link rel="enclosure" type="image/jpeg" href="http://img.example/older.jpg"/>
    <id>tag:chelseafc.com,2026:news:1</id>
    <published>2026-11-12T00:00:00Z</published>
  </entry>
  <entry>
    <title>Newest &lt;script&gt;</title>
    <link rel="alternate" href="https://www.chelseafc.com/en/news/article/newest?a=1&amp;b=2"/>
    <id>tag:chelseafc.com,2026:news:2</id>
    <published>2026-11-13T00:00:00Z</published>
  </entry>
</feed>
"""


def test_parse_feed_keeps_the_feeds_own_order():
    # Dates are estimates (old images get reused), so Chelsea's listing order wins.
    feed = render_html.parse_feed(FEED)
    assert feed["updated"] == "2026-11-13T17:35:47Z"
    assert [e["title"] for e in feed["entries"]] == ["Older & wiser", "Newest <script>"]
    assert feed["entries"][0]["link"] == "https://www.chelseafc.com/en/news/article/older"


def test_alternate_link_wins_over_enclosure():
    older = render_html.parse_feed(FEED)["entries"][0]
    assert older["link"].endswith("/older")


def test_render_escapes_titles_and_links():
    html = render_html.render(render_html.parse_feed(FEED))
    assert "Newest &lt;script&gt;" in html
    assert "<script>" not in html
    assert 'href="https://www.chelseafc.com/en/news/article/newest?a=1&amp;b=2"' in html


def test_render_shows_dates_and_feed_link():
    html = render_html.render(render_html.parse_feed(FEED))
    assert '<time datetime="2026-11-13T00:00:00Z">13 Nov</time>' in html
    assert "Updated 13 Nov 2026, 17:35 UTC" in html
    assert 'href="feed.xml"' in html


def test_render_shows_year_only_when_it_differs_from_the_update():
    feed = {"title": "x", "updated": "2026-11-13T17:35:47Z", "entries": [
        {"title": "a", "link": "https://x/a", "published": "2023-09-12T00:00:00Z"},
        {"title": "b", "link": "https://x/b", "published": "2026-11-12T00:00:00Z"},
    ]}
    html = render_html.render(feed)
    assert ">12 Sep 2023</time>" in html
    assert ">12 Nov</time>" in html


def test_render_handles_empty_feed():
    html = render_html.render({"title": "x", "updated": "", "entries": []})
    assert "No news right now" in html


def test_main_writes_page(tmp_path: Path):
    src = tmp_path / "feed.xml"
    out = tmp_path / "index.html"
    src.write_text(FEED, encoding="utf-8")
    render_html.main(["--feed", str(src), "--out", str(out)])
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
