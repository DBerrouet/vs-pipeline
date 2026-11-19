"""Fetch every enabled feed and insert new stories. Marks near-duplicate titles."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from .config import Feed, Settings
from .store import connect
from .text import canonical_url, jaccard, story_id, strip_html, title_tokens

log = logging.getLogger(__name__)

USER_AGENT = "VeganStartupWeekly-curation/1.0 (+https://veganstartup.substack.com)"
DUP_THRESHOLD = 0.7      # title similarity above which two stories are the same news
DUP_WINDOW_DAYS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6])
    return None


def fetch_feed(feed: Feed, client: httpx.Client) -> list[dict]:
    resp = client.get(feed.url)
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"not a feed: {parsed.bozo_exception}")
    items = []
    for e in parsed.entries:
        link = e.get("link")
        title = strip_html(e.get("title"), 300)
        if not link or not title:
            continue
        body = e.get("summary") or ""
        if not body and e.get("content"):
            body = e["content"][0].get("value", "")
        items.append(
            {
                "url": link,
                "title": title,
                "summary": strip_html(body),
                "published_at": _published(e),
            }
        )
    return items


def insert_items(con, source: str, items: list[dict], now: datetime) -> int:
    recent = con.execute(
        "SELECT id, title FROM stories WHERE coalesce(published_at, fetched_at) >= ?",
        [now - timedelta(days=DUP_WINDOW_DAYS)],
    ).fetchall()
    recent_tokens = [(sid, title_tokens(t)) for sid, t in recent]

    new = 0
    for it in items:
        sid = story_id(it["url"])
        if con.execute("SELECT 1 FROM stories WHERE id = ?", [sid]).fetchone():
            continue
        toks = title_tokens(it["title"])
        dup_of = next((rid for rid, rt in recent_tokens if jaccard(toks, rt) >= DUP_THRESHOLD), None)
        con.execute(
            "INSERT INTO stories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [sid, it["url"], canonical_url(it["url"]), source, it["title"], it["summary"],
             it["published_at"], now, dup_of],
        )
        recent_tokens.append((sid, toks))
        new += 1
    return new


def run(settings: Settings) -> dict[str, int]:
    con = connect(settings.db_path)
    now = _now()
    totals = {}
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for feed in settings.feeds:
            if not feed.enabled:
                continue
            try:
                items = fetch_feed(feed, client)
                n_new = insert_items(con, feed.name, items, now)
                con.execute("INSERT INTO feed_runs VALUES (?, ?, 'ok', ?, ?, NULL)",
                            [feed.name, now, len(items), n_new])
                log.info("%-40s %3d items, %3d new", feed.name, len(items), n_new)
                totals[feed.name] = n_new
            except Exception as exc:  # one broken feed must not stop the others
                con.execute("INSERT INTO feed_runs VALUES (?, ?, 'error', 0, 0, ?)",
                            [feed.name, now, str(exc)[:300]])
                log.warning("%-40s ERROR %s", feed.name, exc)
    con.close()
    return totals
