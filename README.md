# uk.thechels.cfcnews

Chelsea FC's latest news as a fast, lo-fi page and an Atom feed. The page lists each headline with its date and a
link to the story on chelseafc.com. It's about 4 KB, has no JavaScript, works on a phone and follows light or dark
mode. The feed drives the page: each run writes `docs/feed.xml`, then builds `docs/index.html` from it.

Unofficial, and made for my own reading and accessibility needs. It replaces
[cfc_news_as_atom_feed](https://github.com/thechelsuk/cfc_news_as_atom_feed), which now points here.

## Files

- `chelsea_rss.py`: reads Chelsea's news-listing JSON API and writes an Atom 1.0 feed.
- `render_html.py`: reads the feed and writes the page. Standard library only.
- `.github/workflows/update-feed.yml`: runs both every 5 minutes and commits `docs/` and `data/dates.json` if
  anything changed.
- `.github/workflows/test.yml`: the tests, on pushes and pull requests.
- `.github/workflows/release.yml`: tags a release when `version` in `package.json` changes.

## Set-up

1. **Settings → Pages**: deploy from the `main` branch, folder `/docs`.
2. Nothing to set for permissions: the workflow asks for `contents: write` itself.
3. The custom domain is in `docs/CNAME`; the workflow reads it for the feed's self link.

## Dates

Chelsea's listing API has no publish date, but each article page does. The first time an article appears,
`chelsea_rss.py` fetches its page once, reads the date from the article header and keeps it in `data/dates.json`,
so later runs only fetch new stories. Video pages have no date, so those fall back to an estimate from the image
path or upload time. Each entry's summary says which: `date-source:article`, `path-date` or `cloudinary-version`.

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
```

## Caveats

- GitHub's scheduled runs are best-effort and can be late under load.
- The API was found in the site's page source and Chelsea could change or remove it at any time.
