import csv
import io
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote
from zoneinfo import ZoneInfo

UTC = timezone.utc
DEFAULTS = {
    "lookback_hours": 24, "scan_minutes": 5,
    "watchlist": [], "schedule_enabled": False,
    "schedule_time": "12:00", "timezone": "America/New_York",
    "last_schedule_date": "", "intro": "I'm a master's student in the U.S. looking for software engineering opportunities.",
    "role_keywords": "software,engineer,developer,backend,frontend,full stack,full-stack,platform,machine learning,applied AI",
}


def now_iso():
    return datetime.now(UTC).isoformat()


def linkedin_url(value, kind="post"):
    """Only allow canonical LinkedIn profile/post URLs; never arbitrary navigation."""
    try:
        p = urlparse(str(value).strip())
        if p.scheme != "https" or p.hostname not in {"linkedin.com", "www.linkedin.com"} or p.username or p.password or p.port:
            return ""
        path = unquote(p.path)
        if kind == "profile":
            m = re.fullmatch(r"/in/([A-Za-z0-9_%.-]+)/?", path)
            return "https://www.linkedin.com/in/" + m[1] if m else ""
        if re.fullmatch(r"/feed/update/urn:li:(?:activity|share):\d+/?", path) or re.fullmatch(r"/posts/[A-Za-z0-9_%:-]+/?", path):
            return "https://www.linkedin.com" + path.rstrip("/") + "/"
    except (ValueError, TypeError):
        pass
    return ""


def post_key(url):
    m = re.search(r"(?:urn:li:(?:activity|share):|activity-)(\d+)", url)
    return m[1] if m else url.rstrip("/")


def published_time(raw, observed=None):
    """Return UTC datetime and accuracy; never infer a date from an arbitrary number."""
    observed = observed or datetime.now(UTC)
    if not raw:
        return None, "unknown"
    try:
        d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if d.tzinfo:
            return d.astimezone(UTC), "exact"
    except ValueError:
        pass
    raw = str(raw).strip().lower()
    m = re.search(r"(?:^|[\s·•])(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)(?:\b|$)", raw)
    if m:
        unit = m[2][0]
        return observed - timedelta(seconds=int(m[1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]), "approximate"
    if re.search(r"\bjust now\b", raw):
        return observed, "approximate"
    return None, "unknown"


def overlaps_cutoff(raw, published, cutoff):
    """Rounded '1d' might be 47 hours old; don't pass it off as a 24h match."""
    m = re.search(r"(?:^|[\s·•])\d+\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)(?:\b|$)", str(raw).lower())
    if not m:
        return False
    resolution = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[m[1][0]]
    return published >= cutoff and published - timedelta(seconds=resolution) < cutoff


def classify(text, headline="", keywords=None):
    t = text.lower().replace("’", "'")
    roles = [x.strip().lower() for x in (keywords or DEFAULTS["role_keywords"]).split(",") if x.strip()]
    matched = [x for x in roles if re.search(r"\b" + re.escape(x) + r"s?\b", t)]
    hiring = bool(re.search(r"\b(?:we(?:'re| are)|i(?:'m| am)|my team is|our team is)\s+(?:actively\s+)?hiring\b|\bjoin (?:our|my) team\b|\b(?:we(?:'re| are)|i(?:'m| am)) looking for (?:an? |our next )?(?:[\w-]+\s+){0,4}(?:engineer|developer|scientist)\b|\bhiring\s*[:!\-]|#hiring\b", t))
    seeker = bool(re.search(r"\b(?:i(?:'m| am)|i have been) (?:actively )?(?:looking for|seeking) (?:a |an |my next |new )?(?:role|job|opportunity|position)\b|#opentowork\b", t))
    if not hiring or not matched or (seeker and not re.search(r"\b(?:we(?:'re| are)|my team is) hiring\b", t)):
        return 0, [], matched
    reasons = ["Hiring language", "Role match: " + ", ".join(matched[:3])]
    score = 45
    if re.search(r"\b(?:dm me|message me|reach out|send me|let's chat|let’s chat)\b", t):
        score += 25
        reasons.append("Invites a direct conversation")
    if re.search(r"\b(?:founder|cofounder|co-founder|cto|engineering manager|head of engineering)\b", headline.lower()):
        score += 15
        reasons.append("Author headline suggests a hiring decision-maker")
    if re.search(r"\b(?:startup|start-up|founding engineer|small team|seed|series a)\b", t):
        score += 10
        reasons.append("Early-stage team signal")
    if re.search(r"\b(?:united states|u\.s\.|usa|new york|san francisco|boston|seattle)\b", t):
        score += 5
        reasons.append("U.S. location mentioned")
    return min(score, 100), reasons, matched


def schedule_due(settings, now=None):
    if not settings["schedule_enabled"]:
        return False
    local = (now or datetime.now(UTC)).astimezone(ZoneInfo(settings["timezone"]))
    return local.strftime("%H:%M") >= settings["schedule_time"] and settings.get("last_schedule_date") != local.date().isoformat()


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "hiresay.sqlite3"
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS connections (url TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS posts (
              id TEXT PRIMARY KEY, url TEXT NOT NULL, author TEXT, profile_url TEXT, headline TEXT,
              body TEXT, published TEXT, date_accuracy TEXT, date_label TEXT,
              first_seen TEXT, last_seen TEXT, score INTEGER, reasons TEXT, roles TEXT,
              contexts TEXT, sources TEXT, status TEXT DEFAULT 'new');
            CREATE TABLE IF NOT EXISTS scans (
              id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, finished TEXT, state TEXT,
              lookback_hours INTEGER, stats TEXT, note TEXT);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self):
        with self.db() as db:
            return {**DEFAULTS, **{r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM settings")}}

    def save_settings(self, changes, internal=False):
        allowed = set(DEFAULTS) - ({"last_schedule_date"} if not internal else set())
        if not set(changes) <= allowed:
            raise ValueError("Unknown setting")
        s = {**self.settings(), **changes}
        for key, lo, hi in [("lookback_hours", 1, 720), ("scan_minutes", 1, 60)]:
            if type(s[key]) != int or not lo <= s[key] <= hi:
                raise ValueError(f"{key} must be between {lo} and {hi}")
        if type(s["schedule_enabled"]) != bool:
            raise ValueError("Schedule must be true or false")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(s["schedule_time"])):
            raise ValueError("Use a 24-hour time, such as 12:00")
        try:
            ZoneInfo(s["timezone"])
        except Exception as e:
            raise ValueError("Use a valid timezone, such as America/New_York") from e
        if not isinstance(s["watchlist"], list) or len(s["watchlist"]) > 500:
            raise ValueError("Watchlist must contain up to 500 profile URLs")
        cleaned = [linkedin_url(u, "profile") for u in s["watchlist"]]
        if any(not u for u in cleaned):
            raise ValueError("Watchlist accepts https://www.linkedin.com/in/name profile links only")
        for k in ("intro", "role_keywords"):
            if not isinstance(s[k], str) or len(s[k]) > 5000:
                raise ValueError(f"{k} must be text under 5,000 characters")
        s["watchlist"] = list(dict.fromkeys(cleaned))
        with self.db() as db:
            for k in allowed:
                db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (k, json.dumps(s[k])))
        return s

    def import_connections(self, content):
        # LinkedIn's export sometimes starts with prose before its CSV header.
        lines = content.lstrip("\ufeff").splitlines()
        header = next((i for i, line in enumerate(lines) if "First Name" in line and "Last Name" in line), None)
        if header is None:
            raise ValueError("Expected LinkedIn Connections.csv with First Name and Last Name columns")
        count = 0
        with self.db() as db:
            for row in csv.DictReader(io.StringIO("\n".join(lines[header:]))):
                u = linkedin_url(row.get("URL", ""), "profile")
                if u:
                    name = " ".join([row.get("First Name", ""), row.get("Last Name", "")]).strip()
                    db.execute("INSERT OR REPLACE INTO connections VALUES (?,?)", (u, name))
                    count += 1
        return count

    def ingest(self, post, source, cutoff, observed=None):
        observed = observed or datetime.now(UTC)
        url = linkedin_url(post.get("url", ""))
        if not url:
            return "missing_link"
        body = str(post.get("text", ""))[:30000]
        if not body.strip():
            return "unreadable"
        score, reasons, roles = classify(body, str(post.get("headline", "")), self.settings()["role_keywords"])
        if not score:
            return "not_relevant"
        published, accuracy = published_time(post.get("date", ""), observed)
        if published and (published < cutoff or published > observed + timedelta(minutes=5)):
            return "outside_window"
        if published and accuracy == "approximate" and overlaps_cutoff(post.get("date", ""), published, cutoff):
            published, accuracy = None, "unknown"
        key = post_key(url)
        context = str(post.get("context", ""))[:1500]
        profile = linkedin_url(post.get("profile_url", ""), "profile")
        with self.db() as db:
            old = db.execute("SELECT * FROM posts WHERE id=?", (key,)).fetchone()
            contexts = json.loads(old["contexts"]) if old else []
            sources = json.loads(old["sources"]) if old else []
            if context and context not in contexts:
                contexts.append(context)
            if source not in sources:
                sources.append(source)
            # Retain the first estimate so repeated scans don't make rounded dates drift forward.
            if old and old["published"] and accuracy != "exact":
                published = datetime.fromisoformat(old["published"])
                accuracy = old["date_accuracy"]
            values = (url, str(post.get("author", "Unknown author"))[:500], profile, str(post.get("headline", ""))[:1000],
                      body, published.isoformat() if published else None, accuracy, str(post.get("date", ""))[:250],
                      observed.isoformat(), score, json.dumps(reasons), json.dumps(roles), json.dumps(contexts), json.dumps(sources))
            if old:
                db.execute('''UPDATE posts SET url=?,author=?,profile_url=?,headline=?,body=?,published=?,date_accuracy=?,date_label=?,
                last_seen=?,score=?,reasons=?,roles=?,contexts=?,sources=? WHERE id=?''', (*values, key))
            else:
                db.execute('''INSERT INTO posts (url,author,profile_url,headline,body,published,date_accuracy,date_label,last_seen,score,reasons,roles,contexts,sources,id,first_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (*values, key, observed.isoformat()))
        return "duplicate" if old else ("new_unknown_date" if not published else "new")

    def posts(self):
        with self.db() as db:
            rows = db.execute("SELECT p.*, c.name AS connection_name FROM posts p LEFT JOIN connections c ON p.profile_url=c.url ORDER BY p.score DESC, p.published DESC").fetchall()
        out = []
        for r in rows:
            item = dict(r)
            for k in ("reasons", "roles", "contexts", "sources"):
                item[k] = json.loads(item[k])
            out.append(item)
        return out

    def set_status(self, key, status):
        if status not in {"new", "interested", "contacted", "skipped"}:
            raise ValueError("Invalid status")
        with self.db() as db:
            if not db.execute("UPDATE posts SET status=? WHERE id=?", (status, key)).rowcount:
                raise ValueError("Post not found")

    def begin_scan(self, hours):
        with self.db() as db:
            return db.execute("INSERT INTO scans (started,state,lookback_hours,stats,note) VALUES (?,?,?,?,?)", (now_iso(), "running", hours, "{}", "")).lastrowid

    def finish_scan(self, key, state, stats, note):
        with self.db() as db:
            db.execute("UPDATE scans SET finished=?,state=?,stats=?,note=? WHERE id=?", (now_iso(), state, json.dumps(stats), note, key))

    def scans(self):
        with self.db() as db:
            rows = db.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 20").fetchall()
        return [{**dict(r), "stats": json.loads(r["stats"])} for r in rows]
