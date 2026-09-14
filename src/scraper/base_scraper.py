# src/scraper/base_scraper.py
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ScrapedPost:
    id: str
    subreddit: str
    title: str
    body: str
    score: int
    url: str
    created_at: str


@dataclass
class ScrapedComment:
    id: str
    post_id: str
    body: str
    score: int
    created_at: str


class BaseScraper(ABC):
    @abstractmethod
    def scrape(self, **kwargs) -> tuple[list[ScrapedPost], list[ScrapedComment]]:
        """Scrape posts and comments. Returns (posts, comments)."""
        pass
