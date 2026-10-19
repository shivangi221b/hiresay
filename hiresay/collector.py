"""Best-effort visible-page collection. No private API calls or account actions."""
import threading
import time
from collections import Counter
from datetime import datetime, timedelta
from .core import UTC, schedule_due

# LinkedIn ships several DOM variants. Extract only visible cards and their metadata.
# A changed layout is reported as incomplete; it must not produce a false zero-success.
EXTRACT = r"""() => {
  const selectors = ['.feed-shared-update-v2', '[data-testid="mainFeed"] [role="listitem"]'];
  let cards = [...document.querySelectorAll(selectors[0])];
  if (!cards.length) cards = [...document.querySelectorAll(selectors[1])];
  const txt = (e, s) => e.querySelector(s)?.innerText?.trim() || '';
  return cards.map(el => {
    const authorEl = el.querySelector('.update-components-actor__meta-link, a[data-test-app-aware-link][href*="/in/"]');
    const links = [...el.querySelectorAll('a[href]')];
    let url = links.map(a=>a.href).find(u=>/\/feed\/update\/urn:li:(activity|share):\d+|\/posts\/.*activity-\d+/.test(u)) || '';
    if (!url) {
      const urn = el.getAttribute('data-urn') || el.getAttribute('data-id') || '';
      const m = urn.match(/urn:li:(?:activity|share):\d+/);
      if (m) url = 'https://www.linkedin.com/feed/update/' + m[0] + '/';
    }
    let author = txt(el, '.update-components-actor__title span[dir="ltr"], .update-components-actor__title');
    if (!author) {
      const label = [...el.querySelectorAll('[aria-label]')].map(n=>n.getAttribute('aria-label')).find(t=>/post by /i.test(t));
      author = label?.split(/post by /i)[1] || '';
    }
    // Only actor metadata, never arbitrary text from the body/comments, is used for age.
    let date = el.querySelector('time[datetime]')?.getAttribute('datetime') ||
      txt(el, '.update-components-actor__sub-description') || '';
    let context = txt(el, '.update-components-header');
    let body = txt(el, '[data-testid="expandable-text-box"], .update-components-text, .feed-shared-update-v2__description');
    let profile_url = authorEl?.href || '';
    let headline = txt(el, '.update-components-actor__description');
    const reshare = el.querySelector('.update-components-mini-update-v2');
    if (reshare) {
      // The outer timestamp/author may describe the reshare, not the hiring post.
      context = [context, 'Reshared by ' + (author || 'an unidentified person') + '; original date needs checking.'].filter(Boolean).join(' · ');
      date = '';
      author = txt(reshare, '.update-components-actor__title') || 'Original author — check post';
      profile_url = reshare.querySelector('.update-components-actor__meta-link')?.href || '';
      headline = txt(reshare, '.update-components-actor__description');
      body = txt(reshare, '.update-components-text') || body;
      url = reshare.querySelector('a.update-components-mini-update-v2__link-to-details-page')?.href || url;
    }
    return {url, author:author || 'Unknown author', profile_url, headline, text:body, date, context};
  });
}"""


class Collector:
    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.state_lock = threading.Lock()
        self.state = {"busy": False, "action": "idle", "message": "Connect LinkedIn to start collecting.", "session_ready": False}
        # Recover any scan interrupted by closing Terminal / a restart.
        with store.db() as db:
            db.execute("UPDATE scans SET state='interrupted',note='App closed before this scan finished.' WHERE state='running'")

    def status(self):
        with self.state_lock:
            return dict(self.state)

    def update(self, **values):
        with self.state_lock:
            self.state.update(values)

    def start(self, action, hours=None):
        if action not in {"login", "scan"}:
            raise ValueError("Invalid collector action")
        if not self.lock.acquire(blocking=False):
            raise ValueError("A browser task is already running")
        self.cancel.clear()
        self.update(busy=True, action=action, message="Opening your local browser…")
        threading.Thread(target=self.run, args=(action, hours), daemon=True).start()

    @staticmethod
    def authenticated(page):
        return bool(page.locator('a[href*="/mynetwork/"], nav.global-nav, [data-testid="mainFeed"]').count()) and not any(x in page.url for x in ("/login", "/checkpoint/", "/authwall/"))

    def run(self, action, hours):
        scan_id = None
        stats = Counter()
        context = None
        try:
            from playwright.sync_api import sync_playwright
            settings = self.store.settings()
            hours = hours or settings["lookback_hours"]
            if action == "scan":
                scan_id = self.store.begin_scan(hours)
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    str(self.store.root / "browser-profile"), headless=False,
                    viewport={"width": 1280, "height": 900}, accept_downloads=False,
                )
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.set_default_timeout(12000)
                    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(2500)
                    if action == "login":
                        self.update(message="Sign in in the opened browser. Complete any verification yourself; HireSay will save this session locally.")
                        deadline = time.monotonic() + 600
                        while time.monotonic() < deadline and not self.cancel.is_set():
                            if self.authenticated(page):
                                self.update(session_ready=True, message="LinkedIn connected. You can run your first scan.")
                                return
                            page.wait_for_timeout(1000)
                        self.update(message="Sign-in stopped. Click Connect LinkedIn to try again.")
                        return
                    if not self.authenticated(page):
                        self.update(session_ready=False)
                        raise RuntimeError("LinkedIn needs sign-in or verification. Use Connect LinkedIn, then run a new scan.")
                    self.update(session_ready=True)
                    observed = datetime.now(UTC)
                    cutoff = observed - timedelta(hours=hours)
                    sources = [("Your feed", "https://www.linkedin.com/feed/")] + [(u, u + "/recent-activity/all/") for u in settings["watchlist"]]
                    deadline = time.monotonic() + settings["scan_minutes"] * 60
                    seen = set()
                    notes = []
                    for index, (source, url) in enumerate(sources):
                        if self.cancel.is_set() or time.monotonic() >= deadline:
                            break
                        # Divide remaining runtime fairly across remaining sources. No post-count cap.
                        source_deadline = time.monotonic() + (deadline - time.monotonic()) / (len(sources) - index)
                        self.update(message=f"Scanning {source} ({index + 1}/{len(sources)})…")
                        if page.url.rstrip("/") != url.rstrip("/"):
                            page.goto(url, wait_until="domcontentloaded", timeout=45000)
                            page.wait_for_timeout(1800)
                        if any(x in page.url for x in ("/login", "/checkpoint/", "/authwall/")):
                            self.update(session_ready=False)
                            raise RuntimeError("LinkedIn requested verification; scan stopped. Reconnect manually.")
                        idle = 0
                        found_here = 0
                        source_seen = set()
                        while time.monotonic() < source_deadline and not self.cancel.is_set():
                            # Expand only post text. Never open an editor or submit an interaction.
                            more = page.locator('button.feed-shared-inline-show-more-text__see-more-less-toggle, button[aria-label="see more"]')
                            for n in range(min(more.count(), 30)):
                                try:
                                    if more.nth(n).is_visible():
                                        more.nth(n).click(timeout=1000)
                                except Exception:
                                    pass
                            posts = page.evaluate(EXTRACT)
                            added = 0
                            for post in posts:
                                fingerprint = post["url"] or post["text"][:300]
                                if not fingerprint or fingerprint in source_seen:
                                    continue
                                source_seen.add(fingerprint)
                                added += 1
                                found_here += 1
                                # Ingest again across sources to preserve distinct introduction clues.
                                result = self.store.ingest(post, source, cutoff, observed)
                                if fingerprint not in seen:
                                    stats["reviewed"] += 1
                                    stats[result] += 1
                                    seen.add(fingerprint)
                            idle = 0 if added else idle + 1
                            if idle >= 4:
                                break
                            page.evaluate("window.scrollBy(0, Math.round(window.innerHeight * 0.85))")
                            page.wait_for_timeout(2200)
                        stats["sources_visited"] += 1
                        if not found_here:
                            notes.append(f"No readable cards on {source}; layout, access, or loading may have blocked collection.")
                        elif time.monotonic() >= source_deadline:
                            notes.append(f"Runtime allowance reached on {source}.")
                    stats["sources_planned"] = len(sources)
                    note = "Visible-page sample only; LinkedIn's ranked feed cannot guarantee network-wide or 24-hour coverage. "
                    if self.cancel.is_set():
                        note += "Stopped by you. "
                    note += " ".join(notes)
                    usable = stats["reviewed"] - stats["missing_link"] - stats["unreadable"]
                    state = "cancelled" if self.cancel.is_set() else ("partial" if usable else "needs_attention")
                    if not usable:
                        note += " No usable post links with text were collected; the current page layout may need an adapter update."
                    self.store.finish_scan(scan_id, state, dict(stats), note)
                    self.update(message=(f"Scan finished: {stats['new']} new dated matches, {stats['new_unknown_date']} need date verification. Coverage is partial." if usable else "Collection needs attention: no usable posts collected. Open Scan history for details."))
                finally:
                    context.close()
        except ImportError:
            msg = "Playwright is missing. Run Setup.command, then restart HireSay."
            self.update(message=msg)
            if scan_id:
                self.store.finish_scan(scan_id, "failed", dict(stats), msg)
        except Exception as e:
            # No exception trace, HTML, cookies, or credential values go into the dashboard.
            msg = str(e).split("Call log:")[0][:700]
            self.update(message="Browser task stopped: " + msg)
            if scan_id:
                self.store.finish_scan(scan_id, "failed", dict(stats), msg)
        finally:
            self.update(busy=False, action="idle")
            self.lock.release()

    def scheduler(self, stop):
        from zoneinfo import ZoneInfo
        while not stop.wait(15):
            settings = self.store.settings()
            if schedule_due(settings) and not self.status()["busy"]:
                try:
                    self.start("scan")
                    day = datetime.now(ZoneInfo(settings["timezone"])).date().isoformat()
                    self.store.save_settings({"last_schedule_date": day}, internal=True)
                except ValueError:
                    pass
