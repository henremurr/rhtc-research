import os
import sqlite3
import tempfile
import unittest
import asyncio
from unittest.mock import patch

from app.options import news


class NewsPublicationRegressionTest(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"RHTC_DATA_DIR": self.data_dir.name}, clear=False)
        self.env.start()
        with news.connect_db() as connection:
            connection.execute("DELETE FROM news_items")
            connection.execute("DELETE FROM news_meta")

    def tearDown(self):
        self.env.stop()
        self.data_dir.cleanup()

    def insert_story(self, url, *, snippet="", last_seen="2026-10-11T10:00:00-07:00", **metadata):
        values = {
            "url": url,
            "title": "Company announces major infrastructure contract",
            "source": "Test source",
            "published_at": "2026-10-11T09:00:00-07:00",
            "snippet": snippet,
            "peak": "DS/I",
            "first_seen_at": "2026-10-11T09:00:00-07:00",
            "last_seen_at": last_seen,
            "youtube_published": 0,
            "youtube_video_id": "",
            "youtube_url": "",
            "youtube_published_at": "",
            "youtube_privacy_status": "",
            "x_published": 0,
            "x_post_id": "",
            "x_post_url": "",
            "x_published_at": "",
        }
        values.update(metadata)
        with news.connect_db() as connection:
            connection.execute(
                "INSERT INTO news_items(url,title,source,published_at,snippet,peak,first_seen_at,last_seen_at,"
                "youtube_published,youtube_video_id,youtube_url,youtube_published_at,youtube_privacy_status,"
                "x_published,x_post_id,x_post_url,x_published_at) VALUES("
                ":url,:title,:source,:published_at,:snippet,:peak,:first_seen_at,:last_seen_at,"
                ":youtube_published,:youtube_video_id,:youtube_url,:youtube_published_at,:youtube_privacy_status,"
                ":x_published,:x_post_id,:x_post_url,:x_published_at)", values,
            )

    def test_peak_assignment_can_be_changed(self):
        url = "https://example.com/peak-story"
        self.insert_story(url, peak="Other")
        result = asyncio.run(news.update_news_peak(news.NewsPeakInput(url=url, peak="AI/I")))
        self.assertEqual(result["peak"], "AI/I")
        with news.connect_db() as connection:
            row = connection.execute("SELECT peak FROM news_items WHERE url=?", (url,)).fetchone()
        self.assertEqual(row["peak"], "AI/I")

    def test_peak_assignment_rejects_unknown_peak(self):
        self.insert_story("https://example.com/invalid-peak")
        with self.assertRaises(news.HTTPException) as error:
            asyncio.run(news.update_news_peak(news.NewsPeakInput(url="https://example.com/invalid-peak", peak="Unknown")))
        self.assertEqual(error.exception.status_code, 400)

    def test_unpublished_story_can_be_deleted(self):
        url = "https://example.com/unpublished-story"
        self.insert_story(url)
        result = asyncio.run(news.delete_news_story(news.NewsDeleteInput(url=url)))
        self.assertEqual(result["status"], "deleted")
        with news.connect_db() as connection:
            row = connection.execute("SELECT url FROM news_items WHERE url=?", (url,)).fetchone()
        self.assertIsNone(row)

    def test_published_story_cannot_be_deleted(self):
        for suffix, metadata in (
            ("youtube", {"youtube_published": 1}),
            ("x", {"x_published": 1}),
        ):
            with self.subTest(service=suffix):
                url = f"https://example.com/published-{suffix}"
                self.insert_story(url, **metadata)
                with self.assertRaises(news.HTTPException) as error:
                    asyncio.run(news.delete_news_story(news.NewsDeleteInput(url=url)))
                self.assertEqual(error.exception.status_code, 409)
                with news.connect_db() as connection:
                    row = connection.execute("SELECT url FROM news_items WHERE url=?", (url,)).fetchone()
                self.assertIsNotNone(row)

    def test_deduplicate_preserves_x_publication_metadata_from_removed_copy(self):
        keep_url = "https://example.com/story?source=short"
        remove_url = "https://example.net/story?source=long"
        self.insert_story(keep_url, snippet="short")
        self.insert_story(
            remove_url,
            snippet="a much longer snippet, so this duplicate becomes the survivor",
            x_published=1,
            x_post_id="1900123456789",
            x_post_url="https://x.com/i/web/status/1900123456789",
            x_published_at="2026-10-11T11:00:00-07:00",
            youtube_published=1,
            youtube_video_id="youtube123",
            youtube_url="https://youtu.be/youtube123",
            youtube_published_at="2026-10-11T11:05:00-07:00",
            youtube_privacy_status="public",
        )

        result = asyncio.run(news.deduplicate_news())

        self.assertEqual(result["removed"], 1)
        with news.connect_db() as connection:
            row = dict(connection.execute("SELECT * FROM news_items").fetchone())
        self.assertEqual(row["url"], remove_url)
        self.assertEqual(row["x_published"], 1)
        self.assertEqual(row["x_post_id"], "1900123456789")
        self.assertEqual(row["x_post_url"], "https://x.com/i/web/status/1900123456789")
        self.assertEqual(row["x_published_at"], "2026-10-11T11:00:00-07:00")
        self.assertEqual(row["youtube_video_id"], "youtube123")

    def test_url_normalization_migration_preserves_x_and_youtube_metadata(self):
        self.insert_story(
            "https://www.example.com/story?utm_source=old",
            x_published=1,
            x_post_id="1900123456789",
            x_post_url="https://x.com/i/web/status/1900123456789",
            x_published_at="2026-10-11T11:00:00-07:00",
            youtube_published=1,
            youtube_video_id="youtube123",
            youtube_url="https://youtu.be/youtube123",
            youtube_published_at="2026-10-11T11:05:00-07:00",
            youtube_privacy_status="public",
        )
        self.insert_story(
            "https://example.com/story?utm_campaign=new",
            snippet="a later but unpublished copy",
            last_seen="2026-10-11T12:00:00-07:00",
        )
        with news.connect_db() as connection:
            connection.execute("DELETE FROM news_meta WHERE key='url_normalization_version'")

        with news.connect_db() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM news_items")]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://example.com/story")
        self.assertEqual(rows[0]["x_post_id"], "1900123456789")
        self.assertEqual(rows[0]["youtube_video_id"], "youtube123")


    def test_publication_filter_only_counts_complete_youtube_and_x_workflow(self):
        self.insert_story(
            "https://example.com/published",
            youtube_published=1,
            youtube_video_id="video123",
            youtube_url="https://www.youtube.com/watch?v=video123",
            youtube_published_at="2026-10-12T10:00:00-07:00",
            youtube_privacy_status="public",
            x_published=1,
            x_post_id="1900123456789",
            x_post_url="https://x.com/i/web/status/1900123456789",
            x_published_at="2026-10-12T10:01:00-07:00",
        )
        self.insert_story(
            "https://example.com/youtube-only",
            youtube_published=1,
            youtube_video_id="video456",
            youtube_url="https://www.youtube.com/watch?v=video456",
            youtube_privacy_status="public",
        )
        self.insert_story("https://example.com/not-published")

        published = asyncio.run(news.get_news(peak=None, q=None, publication="Published"))
        not_published = asyncio.run(news.get_news(peak=None, q=None, publication="Not published"))

        self.assertEqual([item["url"] for item in published["items"]], ["https://example.com/published"])
        self.assertEqual(
            {item["url"] for item in not_published["items"]},
            {"https://example.com/youtube-only", "https://example.com/not-published"},
        )

    def test_saved_x_record_is_the_status_returned_for_page_reload(self):
        self.insert_story("https://example.com/story")
        request = news.NewsXPublishedInput(
            url="https://www.example.com/story?utm_source=feed",
            post_id="1900123456789",
            post_url="https://x.com/i/web/status/1900123456789",
        )

        saved = asyncio.run(news.mark_news_x_published(request))
        feed = asyncio.run(news.get_news(peak=None, q=None))

        self.assertEqual(saved["status"], "saved")
        self.assertEqual(feed["items"][0]["x_published"], 1)
        self.assertEqual(feed["items"][0]["x_post_id"], "1900123456789")
        self.assertEqual(feed["items"][0]["x_post_url"], request.post_url)

    def test_x_status_save_can_be_retried_without_calling_x_publish_again(self):
        self.insert_story("https://example.com/story")
        request = news.NewsXPublishedInput(
            url="https://example.com/story",
            post_id="1900123456789",
            post_url="https://x.com/i/web/status/1900123456789",
        )
        real_connect_db = news.connect_db
        with patch.object(news, "connect_db", side_effect=sqlite3.OperationalError("temporary database error")):
            with self.assertRaises(sqlite3.OperationalError):
                asyncio.run(news.mark_news_x_published(request))

        retried = asyncio.run(news.mark_news_x_published(request))
        self.assertEqual(retried["status"], "saved")
        with patch.object(news, "connect_db", side_effect=real_connect_db):
            feed = asyncio.run(news.get_news(peak=None, q=None))
        self.assertEqual(feed["items"][0]["x_post_id"], "1900123456789")

    def test_browser_retry_saves_the_confirmed_post_and_blocks_reposting(self):
        with open("app/options/static/app.js", encoding="utf-8") as source:
            script = source.read()

        self.assertIn("const X_PENDING_STORAGE_KEY='rhtc_x_publish_pending_v1'", script)
        self.assertIn("if(pending?.stage==='saved'){await savePendingXPost(card,pending);return}", script)
        save_function = script.split("async function savePendingXPost", 1)[1].split("function restorePendingXPost", 1)[0]
        self.assertIn("/options/api/news/x-published", save_function)
        self.assertNotIn("/options/api/x/publish", save_function)
        self.assertIn("container.querySelectorAll('.news-item').forEach(restorePendingXPost)", script)
        self.assertIn("xPublished=Boolean(Number(item.x_published))", script)
        self.assertIn("if(pending){restorePendingXPost(card);return}", script)


if __name__ == "__main__":
    unittest.main()
