import json

import chelsea_rss as rss

PAGE = (
    '<div data-component="ArticleHeader" data-props="{&quot;articleHeaderDetails&quot;:{&quot;title&quot;:'
    '&quot;Ticket news&quot;,&quot;category&quot;:{&quot;id&quot;:&quot;x&quot;},&quot;date&quot;:'
    '&quot;2026-11-13T15:00:00.0000000\\u002B00:00&quot;,&quot;social&quot;:{}}}"></div>'
    # A fixture widget further down the page has its own dates, which must be ignored.
    '<div data-props="{&quot;kickoffDate&quot;:&quot;Sat 14 Nov 2026&quot;,&quot;date&quot;:&quot;2026-11-14T12:00:00Z&quot;}"></div>'
)

ITEM = {
    "id": "abc",
    "title": "Ticket news",
    "url": "/en/news/article/ticket-news",
    "type": "Article",
    "category": {"title": "Men's Team"},
    # An old, reused image: the estimate would say 2025.
    "thumbnail": {"id": "editorial/news/2025/12/12/x.jpg", "file": {"url": "https://img/v1765533979/x.jpg"}},
}


def test_article_date_reads_the_article_header():
    assert rss.article_date(PAGE) == "2026-11-13T15:00:00Z"


def test_article_date_converts_to_utc():
    page = PAGE.replace("15:00:00.0000000\\u002B00:00", "16:30:00.0000000\\u002B01:00")
    assert rss.article_date(page) == "2026-11-13T15:30:00Z"


def test_article_date_is_none_without_a_header():
    assert rss.article_date("<html>video page</html>") is None


def test_resolve_fetches_each_new_article_once():
    fetched = []

    def fetch(url):
        fetched.append(url)
        return PAGE

    cache = {}
    rss.resolve_dates([ITEM], cache, fetch)
    rss.resolve_dates([ITEM], cache, fetch)
    assert fetched == ["https://www.chelseafc.com/en/news/article/ticket-news"]
    assert cache["abc"] == {"date": "2026-11-13T15:00:00Z", "source": "article"}


def test_resolve_remembers_pages_without_a_date_and_retries_failures():
    calls = []

    def no_date(url):
        calls.append(url)
        return "<html></html>"

    def broken(url):
        calls.append(url)
        raise OSError("timeout")

    cache = {}
    rss.resolve_dates([ITEM], cache, broken)
    assert "abc" not in cache  # a network failure is retried next run
    rss.resolve_dates([ITEM], cache, no_date)
    rss.resolve_dates([ITEM], cache, no_date)
    assert cache["abc"]["date"] is None and cache["abc"]["source"] == "none"
    assert len(calls) == 2  # pages with no date aren't fetched again


def test_resolve_caps_fetches_per_run():
    items = [dict(ITEM, id=str(i), url=f"/en/news/article/{i}") for i in range(5)]
    seen = []
    rss.resolve_dates(items, {}, lambda u: seen.append(u) or PAGE, max_fetch=2)
    assert len(seen) == 2


def test_feed_uses_the_article_date_over_the_estimate():
    xml = rss.build_atom([ITEM], "", dates={"abc": {"date": "2026-11-13T15:00:00Z", "source": "article"}})
    assert "<published>2026-11-13T15:00:00Z</published>" in xml
    assert "date-source:article" in xml


def test_feed_falls_back_to_the_estimate():
    xml = rss.build_atom([ITEM], "", dates={"abc": {"date": None, "source": "none"}})
    assert "<published>2025-12-12T00:00:00Z</published>" in xml


def test_dates_cache_round_trips_and_prunes(tmp_path):
    p = tmp_path / "dates.json"
    rss.save_dates(p, {"a": {"date": "x", "source": "article"}, "old": {"date": "y", "source": "article"}}, keep={"a"})
    assert json.loads(p.read_text()) == {"a": {"date": "x", "source": "article"}}
    assert rss.load_dates(p) == {"a": {"date": "x", "source": "article"}}
    assert rss.load_dates(tmp_path / "missing.json") == {}


NODATE = {"id": "zzz", "title": "Video", "url": "/en/video/x", "type": "Video", "category": {"title": "Men's Team"}}


def test_entry_updated_matches_published_not_run_time():
    xml = rss.build_atom([ITEM], "", dates={"abc": {"date": "2026-11-13T15:00:00Z", "source": "article"}})
    assert "<updated>2026-11-13T15:00:00Z</updated>" in xml.split("<entry>")[1]


def test_feed_updated_is_the_newest_entry_date():
    other = dict(ITEM, id="def")
    dates = {
        "abc": {"date": "2026-11-13T15:00:00Z", "source": "article"},
        "def": {"date": "2026-11-15T09:00:00Z", "source": "article"},
    }
    xml = rss.build_atom([ITEM, other], "", dates=dates)
    assert xml.split("<entry>")[0].count("<updated>2026-11-15T09:00:00Z</updated>") == 1


def test_resolve_records_first_seen_for_undated_pages():
    cache = {}
    rss.resolve_dates([NODATE], cache, lambda u: "<html></html>", now="2026-11-25T10:00:00Z")
    rss.resolve_dates([NODATE], cache, lambda u: "<html></html>", now="2026-11-25T11:00:00Z")
    assert cache["zzz"]["first_seen"] == "2026-11-25T10:00:00Z"


def test_undated_story_uses_first_seen_and_is_stable():
    dates = {"zzz": {"date": None, "source": "none", "first_seen": "2026-11-25T10:00:00Z"}}
    first = rss.build_atom([NODATE], "", dates=dates)
    assert "<published>2026-11-25T10:00:00Z</published>" in first
    assert "<updated>2026-11-25T10:00:00Z</updated>" in first.split("<entry>")[1]
    assert first == rss.build_atom([NODATE], "", dates=dates)


def test_feed_has_an_author():
    xml = rss.build_atom([ITEM], "")
    assert "<author><name>thechelsuk</name></author>" in xml


def test_enclosures_use_https():
    item = dict(ITEM, thumbnail={"file": {"url": "http://img.chelseafc.com/image/upload/v1/x.jpg"}})
    xml = rss.build_atom([item], "")
    assert 'href="https://img.chelseafc.com/image/upload/v1/x.jpg"' in xml
    assert 'href="http://' not in xml
