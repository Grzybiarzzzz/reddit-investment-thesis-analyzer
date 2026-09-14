# src/scraper/reddit_scraper.py
import time
import requests
from datetime import datetime, timezone
from src.scraper.base_scraper import BaseScraper, ScrapedPost, ScrapedComment


class RedditScraper(BaseScraper):
    """Scrapes Reddit via public JSON endpoints. No API key required."""

    BASE_URL = "https://www.reddit.com"

    def __init__(self, user_agent: str = "RedditStockAnalyzer/1.0", delay: float = 3.0):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.delay = delay  # seconds between requests to be respectful

    def _get_json(self, url: str, params: dict = None) -> dict | None:
        """Fetch a Reddit JSON endpoint with rate limiting."""
        time.sleep(self.delay)
        try:
            response = self.session.get(url, params=params, timeout=15)
            if response.status_code == 429:  # rate limited
                retry_after = int(response.headers.get("Retry-After", 60))
                print(f"  Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
                response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"  Error fetching {url}: {e}")
            return None

    def _fetch_posts(self, subreddit: str, sort_mode: str, limit: int) -> list[dict]:
        """Fetch posts from a subreddit listing."""
        url = f"{self.BASE_URL}/r/{subreddit}/{sort_mode}.json"
        data = self._get_json(url, params={"limit": limit, "raw_json": 1})
        if not data or "data" not in data:
            return []
        return data["data"].get("children", [])

    def _fetch_comments(self, subreddit: str, post_id: str) -> list[dict]:
        """Fetch comments for a specific post."""
        url = f"{self.BASE_URL}/r/{subreddit}/comments/{post_id}.json"
        data = self._get_json(url, params={"limit": 100, "depth": 1, "raw_json": 1})
        if not data or not isinstance(data, list) or len(data) < 2:
            return []
        comments_listing = data[1].get("data", {}).get("children", [])
        return [c for c in comments_listing if c.get("kind") == "t1"]

    def scrape(self, subreddits: list[str], sort_modes: list[str],
               posts_per_sort: int, min_comment_score: int,
               ) -> tuple[list[ScrapedPost], list[ScrapedComment]]:
        posts = []
        comments = []
        seen_post_ids = set()
        seen_comment_ids = set()

        for subreddit_name in subreddits:
            for sort_mode in sort_modes:
                if sort_mode not in ("hot", "new", "top", "rising"):
                    continue

                print(f"  Fetching r/{subreddit_name}/{sort_mode}...")
                raw_posts = self._fetch_posts(subreddit_name, sort_mode, posts_per_sort)

                for post_wrapper in raw_posts:
                    post_data = post_wrapper.get("data", {})
                    post_id = post_data.get("id", "")

                    if not post_id or post_id in seen_post_ids:
                        continue
                    seen_post_ids.add(post_id)

                    created_at = datetime.fromtimestamp(
                        post_data.get("created_utc", 0), tz=timezone.utc
                    ).isoformat()

                    posts.append(ScrapedPost(
                        id=post_id,
                        subreddit=post_data.get("subreddit", subreddit_name),
                        title=post_data.get("title", ""),
                        body=post_data.get("selftext", ""),
                        score=post_data.get("score", 0),
                        url=post_data.get("url", ""),
                        created_at=created_at,
                    ))

                    # Fetch comments for this post
                    if post_data.get("num_comments", 0) > 0:
                        raw_comments = self._fetch_comments(subreddit_name, post_id)

                        for comment_wrapper in raw_comments:
                            comment_data = comment_wrapper.get("data", {})
                            comment_id = comment_data.get("id", "")

                            if not comment_id or comment_id in seen_comment_ids:
                                continue
                            if comment_data.get("score", 0) < min_comment_score:
                                continue
                            seen_comment_ids.add(comment_id)

                            comment_created = datetime.fromtimestamp(
                                comment_data.get("created_utc", 0), tz=timezone.utc
                            ).isoformat()

                            comments.append(ScrapedComment(
                                id=comment_id,
                                post_id=post_id,
                                body=comment_data.get("body", ""),
                                score=comment_data.get("score", 0),
                                created_at=comment_created,
                            ))

        return posts, comments
