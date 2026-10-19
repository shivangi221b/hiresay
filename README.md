# HireSay

**A little bird told us you're hiring.**

A free, local dashboard that spots hiring posts in your LinkedIn feed and selected people's activity pages—so you can start a conversation with someone hiring.

**Early prototype:** core logic has automated tests; live LinkedIn collection still needs validation. Layout changes may require collector updates. Every scan has partial coverage.

## What it does

- Finds engineering hiring signals and ranks direct invitations to chat.
- Scans the last **24 hours**, with configurable lookback for backfills; no fixed post-count cap.
- Deduplicates posts and preserves visible connection clues.
- Tracks **Interested / Contacted / Skipped** and prepares editable intro templates on request.
- Optionally scans daily while the app is running and your computer is awake.

No paid API, AI subscription, or automatic outreach. Each person runs their own copy and signs in locally.

## Quick start · macOS

Requires **Python 3.10+**, internet access, and a macOS version supported by [Playwright](https://playwright.dev/python/docs/intro#system-requirements). Setup downloads Chromium and needs several hundred MB of disk space.

1. Clone this repository or download and unzip it using **Code → Download ZIP**.
2. Open **Setup.command** once, then **Start.command**. If double-clicking does not work, run these from the project folder in Terminal:

   ```bash
   bash Setup.command
   bash Start.command
   ```

3. The dashboard opens at **http://127.0.0.1:8765**. Click **Connect LinkedIn** and sign in in the browser that opens.
4. Click **Scan LinkedIn**, then review matches and **Scan history**. Keep Terminal open; press **Control-C** to stop.

In **Sources & settings**, personalize your intro and role keywords, add a few profile URLs to your watchlist, and enable daily scans after your first successful scan. **Explore demo** shows labeled fictional examples without signing in.

## Know before using

- LinkedIn's feed is ranked: this cannot scan every first- or second-degree connection or guarantee all posts from a time window.
- Dates can be approximate. Unverified dates and detected reshares without an original date are flagged for review.
- Scores are heuristics. Company legitimacy, role fit, location, and visa sponsorship are not verified.
- Automated access may violate LinkedIn's terms or result in account restrictions. The collector stops at sign-in walls and does not bypass verification.
- Login sessions and posts stay on your computer. **Never share your browser profile, cookies, connection export, or database.** Share this repository only.

## Documentation

- [Usage, scheduling, privacy & troubleshooting](docs/USAGE.md)
- [Development, tests & project structure](docs/DEVELOPMENT.md)
- [MIT license](LICENSE)

Python + SQLite + Playwright; plain HTML/CSS/JavaScript. No cloud backend or build pipeline.
