# Development

## Run and test

From the repository root (macOS; Linux needs a graphical desktop and Playwright's system dependencies):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m hiresay
```

Core tests use Python's standard library; no LinkedIn login needed:

```bash
python3 -m unittest discover -s tests -v
```

Optional syntax checks if Node is installed:

```bash
node --check web/app.js
bash -n Setup.command Start.command
```

Use `--port 8766` for another port or `--no-open` to suppress opening the dashboard. `HIRESAY_DATA_DIR` sets an isolated runtime data directory. Mac launch scripts are the primary setup route; Linux/Windows installation has not been validated.

## Structure

| Path | Responsibility |
| --- | --- |
| `hiresay/core.py` | SQLite storage, deduplication, dates, ranking, URL/settings validation. |
| `hiresay/collector.py` | Playwright session, visible-card selectors, scan worker, daily scheduling. |
| `hiresay/server.py` | Loopback HTTP API, static assets, request checks, startup. |
| `web/` | Dashboard and labeled fictional demo; no frontend dependencies. |
| `tests/` | Date/backfill boundaries, ranking, dedup/status retention, imports, scheduling, HTTP protections. |

The collector uses a dedicated persistent Chromium profile. Each worker owns its Playwright instance; browser tasks are mutually exclusive. SQLite stores results. Page extraction is the adapter most likely to need updates.

## Validation status

Ten automated tests passed for v0.1. Python, JavaScript, and shell syntax checks passed. Live signed-in LinkedIn collection and browser-rendered dashboard QA remain unverified. A clean-install Mac run and real scan are needed before describing the integration as reliable.

## Contributing

Keep changes focused and run core tests. For collector changes, report which visible layout was tested and preserve partial-coverage reporting. Avoid private APIs, challenge bypasses, and automatic outreach. Never commit profiles, scraped personal data, credentials, or `.env` files. Use synthetic examples in tests and issues.

Source releases should exclude `.git/`, `.venv/`, caches, and runtime data. `.gitignore` helps but does not replace reviewing staged files.

## References

- [Playwright Python](https://playwright.dev/python/docs/library)
- Selector research: [dancolta/linkedin-engage](https://github.com/dancolta/linkedin-engage), [ismaelfi/Scrape-Linkedin-Posts](https://github.com/ismaelfi/Scrape-Linkedin-Posts).

No auto-commenting or publishing pipeline is included. Apify, network-wide enumeration, company verification, and LLM-generated pitches are not implemented.
