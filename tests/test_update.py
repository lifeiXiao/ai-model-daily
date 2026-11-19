import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("update", Path(__file__).resolve().parents[1] / "scripts/update.py")
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)

class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 19, 0, 17, tzinfo=timezone.utc)
        self.source = {"org": "example", "name": "Example"}
        self.news = {"id": "test-news", "name": "Example", "url": "https://www.anthropic.com/news"}

    def model(self, **kwargs):
        data = {"id": "example/Model-A", "createdAt": "2026-11-18T12:00:00Z",
                "lastModified": "2026-11-19T01:00:00Z", "pipeline_tag": "text-generation",
                "tags": ["license:apache-2.0", "conversational"]}
        data.update(kwargs)
        return u.model_record(data, self.source)

    def test_gzip_feed_is_decoded(self):
        import gzip
        payload = b"<rss><channel/></rss>"
        self.assertEqual(u.decode_body(gzip.compress(payload)), payload.decode())

    def test_creation_is_not_last_modified(self):
        self.assertEqual(self.model()["published_at"], "2026-11-18T12:00:00Z")
        self.assertIsNone(self.model(createdAt=None))

    def test_only_configured_owner(self):
        self.assertIsNone(self.model(id="other/Model-A"))

    def test_license_and_task_are_explicit(self):
        model = self.model()
        self.assertEqual(model["license"], "apache-2.0")
        self.assertEqual(model["task"], "文本生成")
        self.assertIn("对话", model["features"])

    def test_unknown_task_has_no_invented_capabilities(self):
        model = self.model(pipeline_tag="new-task")
        self.assertEqual(model["task"], "其他任务")
        self.assertIn("模型卡", model["summary"])

    def test_merge_preserves_first_seen_and_deduplicates(self):
        first = self.model()
        first["first_seen_at"] = "2026-11-18T13:00:00Z"
        result = u.merge([first], [self.model(), self.model()], self.now)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["first_seen_at"], first["first_seen_at"])

    def test_source_failure_preserves_previous_rows(self):
        old = self.model()
        self.assertEqual(u.merge([old], [], self.now)[0]["id"], old["id"])

    def test_retention_and_future_dates(self):
        old = self.model(createdAt="2020-01-01T00:00:00Z")
        future = self.model(id="example/future", createdAt="2030-01-01T00:00:00Z")
        self.assertEqual(u.merge([], [old, future], self.now), [])

    def test_rss_filters_company_news(self):
        text = """<rss><channel>
        <item><title>Introducing GPT-6</title><link>https://example.com/model</link>
        <pubDate>Wed, 18 Nov 2026 12:00:00 GMT</pubDate><description>&lt;b&gt;New capabilities&lt;/b&gt;</description></item>
        <item><title>New office opening</title><link>https://example.com/office</link>
        <pubDate>Wed, 18 Nov 2026 12:00:00 GMT</pubDate></item>
        </channel></rss>"""
        rows = u.parse_rss(text, self.news)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["summary"], "New capabilities")

    def test_atom_feed(self):
        text = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>Introducing Gemini Next</title><link href="https://example.com/gemini"/>
        <published>2026-11-18T12:00:00Z</published><summary>Multimodal model</summary>
        </entry></feed>"""
        self.assertEqual(len(u.parse_rss(text, self.news)), 1)

    def test_anthropic_date_and_sibling_title(self):
        text = """<ul><li><a href="/news/claude-next"><h3>Introducing Claude Next</h3></a>
        <p>Nov 18, 2026</p></li></ul>"""
        rows = u.parse_anthropic(text, self.news)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["published_at"], "2026-11-18T00:00:00Z")

    def test_changed_html_fails_loudly(self):
        with self.assertRaises(ValueError):
            u.parse_anthropic("<html>Website changed</html>", self.news)

    def test_non_https_news_is_rejected(self):
        self.assertIsNone(u.announcement("Claude Next", "javascript:alert(1)", "Nov 18, 2026", "", self.news))

    def test_extract_is_short_plain_text(self):
        text = u.excerpt("<script>ignored()</script>" + " word" * 200)
        self.assertNotIn("<script>", text)
        self.assertLessEqual(len(text.split()), 45)
        self.assertLessEqual(len(text), 300)

if __name__ == "__main__":
    unittest.main()
