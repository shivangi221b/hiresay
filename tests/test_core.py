import json
import tempfile
import unittest
from datetime import datetime, timedelta
from hiresay.core import Store, UTC, DEFAULTS, classify, linkedin_url, post_key, published_time, schedule_due


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.now = datetime(2026, 10, 18, 16, tzinfo=UTC)
        self.cutoff = self.now - timedelta(hours=24)
        self.post = {"url":"https://www.linkedin.com/feed/update/urn:li:activity:123456789/", "author":"Jane Example",
                     "profile_url":"https://www.linkedin.com/in/jane-example/", "headline":"Founder at Example",
                     "text":"We're hiring a software engineer in New York. Small team. DM me to chat.", "date":"2h", "context":"Sam commented on this"}

    def ingest(self, post=None, source="feed", now=None):
        return self.store.ingest(post or self.post, source, self.cutoff, now or self.now)

    def test_hiring_vs_jobseeker(self):
        score, reasons, roles = classify(self.post["text"], self.post["headline"])
        self.assertEqual(score, 100)
        self.assertIn("Invites a direct conversation", reasons)
        self.assertGreater(classify("We’re hiring backend engineers. DM me.")[0], 0)
        self.assertEqual(classify("I'm looking for a software engineer role. #OpenToWork #Hiring")[0], 0)
        self.assertEqual(classify("We're hiring a pastry chef. DM me.")[0], 0)
        self.assertEqual(classify("I love software engineering. Is anyone hiring?")[0], 0)

    def test_dates_and_backfill(self):
        self.assertEqual(self.ingest(), "new")
        old = {**self.post,"url":"https://www.linkedin.com/feed/update/urn:li:activity:222/","date":"3d"}
        self.assertEqual(self.ingest(old), "outside_window")
        self.assertEqual(self.store.ingest(old,"watchlist",self.now-timedelta(days=7),self.now),"new")
        boundary = {**self.post,"url":"https://www.linkedin.com/feed/update/urn:li:activity:333/","date":"1d"}
        self.assertEqual(self.ingest(boundary),"new_unknown_date")
        unknown = {**self.post,"url":"https://www.linkedin.com/feed/update/urn:li:activity:444/","date":"Edited · 35 likes"}
        self.assertEqual(self.ingest(unknown), "new_unknown_date")
        rows = {p['id']:p for p in self.store.posts()}
        self.assertIsNone(rows['333']['published'])
        self.assertIsNone(rows['444']['published'])
        self.assertEqual(published_time("2026-10-18T10:00:00Z")[1],"exact")
        self.assertEqual(published_time("2026-10-18T10:00:00")[1],"unknown")

    def test_dedup_preserves_status_context_and_first_date(self):
        self.ingest()
        first = self.store.posts()[0]
        self.store.set_status(first["id"], "interested")
        again = {**self.post,"url":"https://www.linkedin.com/posts/jane_activity-123456789-abcd?trackingId=x", "context":"Taylor liked this"}
        self.assertEqual(self.ingest(again, "watchlist", self.now + timedelta(minutes=20)), "duplicate")
        rows = self.store.posts()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "interested")
        self.assertEqual(rows[0]["first_seen"], first["first_seen"])
        self.assertEqual(rows[0]["published"], first["published"])
        self.assertEqual(rows[0]["contexts"], ["Sam commented on this", "Taylor liked this"])
        self.assertEqual(rows[0]["sources"], ["feed", "watchlist"])

    def test_url_validation(self):
        for bad in ["http://www.linkedin.com/in/jane", "https://linkedin.com.evil.test/in/jane", "javascript:alert(1)", "https://www.linkedin.com@evil.test/in/jane", "https://www.linkedin.com:443/in/jane", "https://www.linkedin.com/in/jane/../../login"]:
            self.assertEqual(linkedin_url(bad, "profile"), "")
        self.assertEqual(linkedin_url("https://www.linkedin.com/in/jane/?tracking=123","profile"),"https://www.linkedin.com/in/jane")
        self.assertEqual(post_key(self.post["url"]), "123456789")

    def test_connection_import_only_labels_actual_known_authors(self):
        self.ingest()
        csv = 'Notes about the export\n\nFirst Name,Last Name,URL,Email Address\nJane,Example,https://www.linkedin.com/in/jane-example/,ignored@example.test\nBad,Link,https://evil.test/in/x/,\n'
        self.assertEqual(self.store.import_connections(csv),1)
        self.assertEqual(self.store.posts()[0]["connection_name"],"Jane Example")
        with self.store.db() as db:
            self.assertEqual([x[1] for x in db.execute("PRAGMA table_info(connections)")],["url","name"])

    def test_settings_validate_all_before_write(self):
        with self.assertRaises(ValueError):
            self.store.save_settings({"scan_minutes":5,"watchlist":["https://evil.test"]})
        self.assertEqual(self.store.settings()["watchlist"], [])
        for invalid in [{"scan_minutes":0},{"schedule_time":"24:00"},{"timezone":"bogus"},{"schedule_enabled":"yes"},{"last_schedule_date":"fake"}]:
            with self.assertRaises(ValueError):
                self.store.save_settings(invalid)
        self.store.save_settings({"watchlist":["https://www.linkedin.com/in/jane/"]})
        self.assertEqual(self.store.settings()["watchlist"],["https://www.linkedin.com/in/jane"])

    def test_scheduler_once_per_day_and_dst(self):
        s = {**DEFAULTS,"schedule_enabled":True}
        self.assertTrue(schedule_due(s, self.now)) # 12:00 New York in October
        self.assertFalse(schedule_due(s,self.now-timedelta(minutes=1)))
        self.assertFalse(schedule_due({**s,"last_schedule_date":"2026-10-18"},self.now))
        winter = datetime(2026,12,1,16,59,tzinfo=UTC)
        self.assertFalse(schedule_due(s,winter))
        self.assertTrue(schedule_due(s,winter+timedelta(minutes=1)))

    def test_interrupted_scan_recovery(self):
        from hiresay.collector import Collector
        self.store.begin_scan(24)
        Collector(self.store)
        self.assertEqual(self.store.scans()[0]['state'], 'interrupted')


if __name__ == '__main__':
    unittest.main()
