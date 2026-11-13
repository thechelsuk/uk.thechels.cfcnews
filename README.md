# uk.thechels.cfcnews

Chelsea FC's latest news as a fast, lo-fi page and an Atom feed. The page lists each headline with its date and a
link to the story on chelseafc.com. It's about 4 KB, has no JavaScript, works on a phone and follows light or dark
mode. The feed drives the page: each run writes `docs/feed.xml`, then builds `docs/index.html` from it.

Unofficial, and made for my own reading and accessibility needs. It replaces
[cfc_news_as_atom_feed](https://github.com/thechelsuk/cfc_news_as_atom_feed), which now points here.

## Files

- `chelsea_rss.py`: reads Chelsea's news-listing JSON API and writes an Atom 1.0 feed.
- `render_html.py`: reads the feed and writes the page. Standard library only.
- `.github/workflows/update-feed.yml`: runs both every 5 minutes and commits `docs/` if anything changed.
- `.github/workflows/test.yml`: the tests, on pushes and pull requests.
- `.github/workflows/release.yml`: tags a release when `version` in `package.json` changes.

## Set-up

1. **Settings → Pages**: deploy from the `main` branch, folder `/docs`.
2. **Settings → Actions → General → Workflow permissions**: read and write, so the workflow can push `docs/`.
3. Once the DNS record for the custom domain exists, add it under **Settings → Pages → Custom domain** and set the
   repository variable `SITE_URL` (for example `https://cfcnews.thechels.uk`) so the feed's self link matches.

## Dates

Chelsea's API has no publish date, so `chelsea_rss.py` estimates one from the image path or upload time. Old
stories sometimes reuse old images, so the page keeps Chelsea's own order rather than sorting by date, and shows
the year on any date outside the current one.

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
```

## Caveats

- GitHub's scheduled runs are best-effort and can be late under load.
- The API was found in the site's page source and Chelsea could change or remove it at any time.
