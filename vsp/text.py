"""Small text helpers: URL canonicalisation, HTML stripping, title similarity."""
from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|source$)")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_WORD = re.compile(r"[a-z0-9$€£¥]+")
_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "its",
    "is", "as", "at", "by", "from", "new", "after", "into", "it", "be", "has",
}


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k.lower())]
    path = parts.path.rstrip("/") or "/"
    host = parts.netloc.lower().removeprefix("www.")
    return urlunsplit(("https", host, path, urlencode(query), ""))


def story_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode()).hexdigest()[:16]


def strip_html(text: str | None, limit: int = 1500) -> str:
    if not text:
        return ""
    out = _WS.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()
    return out[:limit]


def title_tokens(title: str) -> set[str]:
    # Google News appends " - Outlet Name"; drop it.
    title = re.sub(r"\s+[-–|]\s+[^-–|]{2,40}$", "", title)
    return {w for w in _WORD.findall(title.lower()) if w not in _STOP}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def norm_company(name: str | None) -> str:
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r"\b(inc|ltd|gmbh|sas|ag|llc|co|corp|group|foods?)\b\.?", "", name)
    return re.sub(r"[^a-z0-9]", "", name)
