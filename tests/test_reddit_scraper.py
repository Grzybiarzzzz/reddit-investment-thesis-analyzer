# tests/test_reddit_scraper.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from src.scraper.reddit_scraper import RedditScraper
from src.scraper.base_scraper import ScrapedPost, ScrapedComment


def _make_post_response(post_id="abc123", title="AAPL to the moon",
                        selftext="Great earnings", author="user1",
                        score=50, subreddit="stocks", num_comments=5):
    return {
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": post_id,
                        "title": title,
                        "selftext": selftext,
                        "author": author,
                        "score": score,
                        "subreddit": subreddit,
                        "url": f"http://reddit.com/{post_id}",
                        "created_utc": datetime.now(timezone.utc).timestamp(),
                        "num_comments": num_comments,
                    }
                }
            ]
        }
    }


def _make_comments_response(comment_id="comm1", body="AAPL fundamentals are strong",
                            author="user2", score=10):
    return [
        {"data": {"children": []}},  # post data (index 0)
        {
            "data": {
                "children": [
                    {
                        "kind": "t1",
                        "data": {
                            "id": comment_id,
                            "body": body,
                            "author": author,
                            "score": score,
                            "created_utc": datetime.now(timezone.utc).timestamp(),
                        }
                    }
                ]
            }
        }
    ]


class TestRedditScraper:
    @patch("src.scraper.reddit_scraper.time.sleep")  # skip delays in tests
    @patch("src.scraper.reddit_scraper.requests.Session")
    def test_scrape_returns_posts(self, mock_session_cls, mock_sleep):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = _make_post_response()

        comment_resp = MagicMock()
        comment_resp.status_code = 200
        comment_resp.json.return_value = _make_comments_response()

        mock_session.get.side_effect = [post_resp, comment_resp]

        scraper = RedditScraper(user_agent="test", delay=0)
        posts, comments = scraper.scrape(
            subreddits=["stocks"],
            sort_modes=["hot"],
            posts_per_sort=10,
            min_comment_score=3,
        )

        assert len(posts) == 1
        assert isinstance(posts[0], ScrapedPost)
        assert posts[0].id == "abc123"
        assert posts[0].subreddit == "stocks"

    @patch("src.scraper.reddit_scraper.time.sleep")
    @patch("src.scraper.reddit_scraper.requests.Session")
    def test_scrape_returns_comments(self, mock_session_cls, mock_sleep):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = _make_post_response()

        comment_resp = MagicMock()
        comment_resp.status_code = 200
        comment_resp.json.return_value = _make_comments_response()

        mock_session.get.side_effect = [post_resp, comment_resp]

        scraper = RedditScraper(user_agent="test", delay=0)
        posts, comments = scraper.scrape(
            subreddits=["stocks"],
            sort_modes=["hot"],
            posts_per_sort=10,
            min_comment_score=3,
        )

        assert len(comments) == 1
        assert isinstance(comments[0], ScrapedComment)
        assert comments[0].post_id == "abc123"

    @patch("src.scraper.reddit_scraper.time.sleep")
    @patch("src.scraper.reddit_scraper.requests.Session")
    def test_filters_low_score_comments(self, mock_session_cls, mock_sleep):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = _make_post_response()

        comment_resp = MagicMock()
        comment_resp.status_code = 200
        comment_resp.json.return_value = _make_comments_response(score=1)

        mock_session.get.side_effect = [post_resp, comment_resp]

        scraper = RedditScraper(user_agent="test", delay=0)
        _, comments = scraper.scrape(
            subreddits=["stocks"],
            sort_modes=["hot"],
            posts_per_sort=10,
            min_comment_score=3,
        )

        assert len(comments) == 0

    @patch("src.scraper.reddit_scraper.time.sleep")
    @patch("src.scraper.reddit_scraper.requests.Session")
    def test_deduplicates_posts(self, mock_session_cls, mock_sleep):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = _make_post_response()

        comment_resp = MagicMock()
        comment_resp.status_code = 200
        comment_resp.json.return_value = _make_comments_response()

        # hot returns the post + comments, new returns the same post + comments
        mock_session.get.side_effect = [post_resp, comment_resp, post_resp, comment_resp]

        scraper = RedditScraper(user_agent="test", delay=0)
        posts, _ = scraper.scrape(
            subreddits=["stocks"],
            sort_modes=["hot", "new"],
            posts_per_sort=10,
            min_comment_score=3,
        )

        assert len(posts) == 1
