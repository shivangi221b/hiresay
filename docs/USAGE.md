# Using HireSay

## Collect → review → reach out

1. **Connect LinkedIn.** Sign in directly, including two-factor verification. The dedicated browser closes when HireSay detects a signed-in session. No credentials go into the dashboard or chat.
2. **Scan.** Leave the collector browser alone while it reads visible post cards from your feed and watchlist activity pages.
3. **Review.** Open the original post, verify its date and role, and choose Interested, Contacted, or Skipped. The same post keeps its status across scans.
4. **Draft intro.** This uses your editable introduction in a rule-based template. Personalize it and send it yourself; HireSay never sends messages, likes, or comments.

Each friend installs and runs their own copy. No one needs your LinkedIn account or runtime data.

## Settings

| Setting | Default / behavior |
| --- | --- |
| Lookback | 24 hours; configurable from 1–720 hours. Wider windows backfill unseen posts. |
| Dashboard window | 24 hours, 3 / 7 / 30 days, or All saved. Scanning from All saved uses the configured default. |
| Runtime budget | 5 minutes, configurable from 1–60. Shared across feed and watchlist; collection also stops after repeated scrolling yields nothing new. |
| Watchlist | Empty initially. Start with 5–10 profile URLs, one per line. Hundreds leave little time per source. |
| Role keywords | Engineering terms, comma-separated. Hiring intent plus a role keyword is required. |
| Daily schedule | Off initially. Default time: 12:00, America/New_York. |
| Introduction | Replace the sample student introduction with your own background before drafting. |

There is no fixed post-count cap, but runtime and LinkedIn's ranked feed limit coverage. A larger lookback doesn't guarantee older posts will surface. Exclude date-unverified posts using the dashboard checkbox. English hiring expressions and relative dates are supported initially.

Optional **Connections.csv** import matches authors to known first-degree connections; only names and profile URLs are stored. It does not enumerate second-degree connections or access anyone else's home feed. A visible like/comment is an introduction clue, not a verified relationship or promised introduction.

## Scheduling

Keep **Start.command running**, your computer awake, and internet available. If HireSay opens after the scheduled time, it attempts today's scan then. Failed attempts appear in history; retry manually after addressing the problem. Each installation has its own schedule. No background service, login item, email, or desktop notification is installed.

## Privacy and resetting

Mac data lives outside the repository at `~/Library/Application Support/HireSay/`:

- `hiresay.sqlite3`: posts, statuses, settings, imported connection names/URLs.
- `browser-profile/`: the sensitive, signed-in browser session.

Stop HireSay before removing data. Remove `browser-profile/` to reset login; remove the whole HireSay data folder to reset everything. These actions permanently delete the corresponding local data.

The dashboard binds to `127.0.0.1`, checks Host/Origin on writes, and loads no external analytics or scripts. LinkedIn requests still use the internet. HireSay adds no database encryption; OS account security and disk encryption protect local files. It is not designed for public hosting or shared computers.

Linux data lives at `$XDG_DATA_HOME/hiresay` or `~/.local/share/hiresay`. `HIRESAY_DATA_DIR` overrides it for development. Never put session data in a shared repository, even with `.gitignore` protections.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Python missing / too old | Install Python 3.10+ from [python.org](https://www.python.org/downloads/macos/), then rerun Setup.command. |
| Browser won't open | Rerun Setup.command and inspect installation errors; Chromium and a supported OS are required. |
| Sign-in / verification wall | Reconnect and complete it manually. Don't keep retrying a blocked scan. |
| No usable cards or links | Check Scan history. LinkedIn markup may need a collector update; this does not mean nobody is hiring. |
| Cards reviewed but no matches | Try a wider window or adjust keywords/watchlist. The visible sample may lack matching posts. |
| Old feed posts | Expected. The collector filters each card's date and continues past old cards. |
| Daily scan missed | Check the app is running, computer awake, session valid, and timezone correct. |
| Port already used | Open the existing dashboard or run `.venv/bin/python -m hiresay --port 8766`. |

For bug reports, include OS/Python versions, steps, non-sensitive scan counts, and the error message. Redact personal details. Don't attach cookies, session folders, databases, or connection exports.
