from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models import Feed, Website
from src.services.rate_limiter import RateLimiter

logger = structlog.get_logger()

COMMON_FEED_PATHS = [
    "/feed",
    "/rss",
    "/atom.xml",
    "/feed.xml",
    "/rss.xml",
    "/index.xml",
    "/feeds/all.atom.xml",
]

RSS_CONTENT_TYPES = {
    "application/rss+xml",
    "application/atom+xml",
    "application/xml",
    "text/xml",
}


class _LinkTagParser(HTMLParser):
    """Extract RSS/Atom <link> tags from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.feed_links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "link":
            return
        attr = dict(attrs)
        rel = (attr.get("rel") or "").lower()
        link_type = (attr.get("type") or "").lower()
        href = attr.get("href") or ""
        if rel == "alternate" and link_type in ("application/rss+xml", "application/atom+xml") and href:
            self.feed_links.append((href, link_type))


def _feed_type_from_content_type(content_type: str) -> str:
    ct = content_type.lower()
    if "atom" in ct:
        return "atom"
    return "rss"


class FeedDiscoveryService:
    def __init__(self, http_client: httpx.AsyncClient, rate_limiter: RateLimiter) -> None:
        self.http_client = http_client
        self.rate_limiter = rate_limiter

    async def discover_feeds(self, website: Website, db: AsyncSession) -> list[Feed]:
        domain = urlparse(website.url).netloc
        log = logger.bind(website_id=website.id, domain=domain)

        candidates: list[tuple[str, str]] = []

        try:
            await self.rate_limiter.acquire(domain)
            response = await self.http_client.get(website.url, follow_redirects=True)
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "60"))
                await self.rate_limiter.notify_retry_after(domain, retry_after)
                website.discovery_status = "error"
                await db.commit()
                return []
            response.raise_for_status()
            html = response.text

            parser = _LinkTagParser()
            try:
                parser.feed(html)
            except Exception:
                log.warning("html_parse_error", msg="Failed to parse homepage HTML")

            base_url = str(response.url)
            for href, link_type in parser.feed_links:
                absolute_url = urljoin(base_url, href)
                feed_type = "atom" if "atom" in link_type else "rss"
                candidates.append((absolute_url, feed_type))

        except httpx.HTTPError as exc:
            log.warning("discovery_network_error", error=str(exc))
            website.discovery_status = "error"
            await db.commit()
            return []

        parsed_base = urlparse(website.url)
        base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
        for path in COMMON_FEED_PATHS:
            candidates.append((base_origin + path, ""))

        new_feeds: list[Feed] = []
        seen_urls: set[str] = set()

        for url, feed_type_hint in candidates:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            validated_type = await self._validate_feed_url(url, feed_type_hint, domain)
            if validated_type is None:
                continue

            feed = Feed(
                website_id=website.id,
                feed_url=url,
                title=None,
                feed_type=validated_type or feed_type_hint or None,
            )
            db.add(feed)
            try:
                await db.flush()
                new_feeds.append(feed)
                log.info("feed_discovered", feed_url=url)
            except IntegrityError:
                await db.rollback()
                log.debug("feed_already_exists", feed_url=url)

        website.last_discovery_at = datetime.now(timezone.utc).replace(tzinfo=None)
        website.discovery_status = "found" if new_feeds else "not_found"

        existing_result = await db.execute(select(Feed).where(Feed.website_id == website.id))
        all_feeds = existing_result.scalars().all()
        if all_feeds and not new_feeds:
            website.discovery_status = "found"

        await db.commit()

        for feed in new_feeds:
            await db.refresh(feed)

        return new_feeds

    async def _validate_feed_url(self, url: str, feed_type_hint: str, domain: str) -> str | None:
        """Return feed type string if URL is a valid feed, else None."""
        url_domain = urlparse(url).netloc
        try:
            await self.rate_limiter.acquire(url_domain)
            response = await self.http_client.head(url, follow_redirects=True)
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "60"))
                await self.rate_limiter.notify_retry_after(url_domain, retry_after)
                return None
            if response.status_code not in (200, 301, 302, 307, 308):
                return None
            content_type = response.headers.get("content-type", "")
            for ct in RSS_CONTENT_TYPES:
                if ct in content_type:
                    return _feed_type_from_content_type(content_type)
            # Try GET if HEAD gives ambiguous content-type
            await self.rate_limiter.acquire(url_domain)
            get_response = await self.http_client.get(url, follow_redirects=True)
            if get_response.status_code != 200:
                return None
            content_type = get_response.headers.get("content-type", "")
            for ct in RSS_CONTENT_TYPES:
                if ct in content_type:
                    return _feed_type_from_content_type(content_type)
            body = get_response.text[:500]
            if "<rss" in body or "<feed" in body or "<channel" in body:
                return feed_type_hint or "rss"
            return None
        except httpx.HTTPError:
            return None
