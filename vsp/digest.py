"""Build the Monday digest: pick the lead, fill sections, write HTML + Markdown to docs/."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .config import Settings
from .render import render_html, render_markdown
from .store import connect
from .text import norm_company

log = logging.getLogger(__name__)

SECTION_ORDER = ["money_moves", "launch_radar", "regulation", "exits_shutdowns"]
SECTION_TITLES = {
    "money_moves": "Money moves",
    "launch_radar": "Launch radar",
    "regulation": "Regulation watch",
    "exits_shutdowns": "Exits and shutdowns",
    "market_data": "One number",
}


@dataclass
class Item:
    id: str
    url: str
    source: str
    title: str
    published_at: datetime | None
    tier: str
    section: str
    company: str
    country: str
    amount_text: str
    relevance: int
    headline: str
    one_line: str
    summary: str
    why_it_matters: str
    key_number: str
    leaves_vegan: bool
    also: list[tuple[str, str]] = field(default_factory=list)  # (source, url) of merged duplicates

    @property
    def label(self) -> str:
        name = self.company or self.headline
        return f"{name} ({self.country})" if self.country else name


@dataclass
class Digest:
    generated_on: date
    window_start: date
    window_end: date
    subject: str
    preview: str
    lead: Item | None
    sections: dict[str, list[Item]]
    one_number: Item | None
    candidates: list[Item]
    skipped: list[Item]
    feed_health: list[tuple]
    closing_line: str
    newsletter_name: str


def load_items(con, since: datetime) -> list[Item]:
    rows = con.execute(
        """
        SELECT s.id, s.url, s.source, s.title, s.published_at,
               c.tier, c.section, c.company, c.country, c.amount_text, c.relevance,
               c.headline, c.one_line, c.summary, c.why_it_matters, c.key_number, c.leaves_vegan
        FROM stories s JOIN classifications c ON c.story_id = s.id
        WHERE coalesce(s.published_at, s.fetched_at) >= ?
        """,
        [since],
    ).fetchall()
    items = [Item(*r) for r in rows]
    for it in items:
        it.relevance = it.relevance or 0
        for f in ("company", "country", "amount_text", "headline", "one_line", "summary",
                  "why_it_matters", "key_number"):
            setattr(it, f, (getattr(it, f) or "").strip())
    # Attach the URLs of title-level duplicates (skipped at classification) as extra sources.
    dups = con.execute(
        "SELECT duplicate_of, source, url FROM stories WHERE duplicate_of IS NOT NULL AND fetched_at >= ?",
        [since - timedelta(days=3)],
    ).fetchall()
    by_id = {it.id: it for it in items}
    for parent, source, url in dups:
        if parent in by_id and url != by_id[parent].url:
            by_id[parent].also.append((source, url))
    return items


def merge_same_story(items: list[Item]) -> list[Item]:
    """Same company + same section in one week = one story. Keep the best-scored version."""
    groups: dict[tuple[str, str], list[Item]] = {}
    singles = []
    for it in items:
        key = norm_company(it.company)
        if not key or it.section in ("skip", "market_data"):
            singles.append(it)
            continue
        groups.setdefault((key, it.section), []).append(it)
    merged = []
    for group in groups.values():
        # Prefer direct outlets over Google News redirects when scores tie.
        group.sort(key=lambda i: (i.relevance, not i.source.startswith("Google News")), reverse=True)
        best = group[0]
        for other in group[1:]:
            best.also.append((other.source, other.url))
            best.also.extend(other.also)
        merged.append(best)
    return merged + singles


def pick_lead(items: list[Item], min_rel: int, margin: int) -> Item | None:
    eligible = [i for i in items if i.section not in ("skip", "market_data") and i.relevance >= min_rel]
    core = max((i for i in eligible if i.tier == "core"), key=lambda i: i.relevance, default=None)
    adj = max((i for i in eligible if i.tier == "adjacent"), key=lambda i: i.relevance, default=None)
    if core and adj and adj.relevance >= core.relevance + margin:
        return adj
    return core or adj


def _rank(i: Item) -> tuple:
    # Core stories get +1 so they come first unless an adjacent one is clearly bigger;
    # ties go to core, then to the most recent.
    is_core = i.tier == "core"
    return (i.relevance + (1 if is_core else 0), is_core, i.published_at or datetime.min)


def build(settings: Settings, today: date | None = None) -> Digest:
    con = connect(settings.db_path)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today = today or now.date()
    since = now - timedelta(days=settings.digest_lookback_days)

    items = merge_same_story(load_items(con, since))
    in_scope = [i for i in items if i.tier in ("core", "adjacent") or i.leaves_vegan]
    skipped = sorted((i for i in items if i not in in_scope or i.section == "skip"),
                     key=lambda i: -i.relevance)
    usable = [i for i in in_scope if i.section != "skip"]

    lead = pick_lead(usable, settings.min_relevance, settings.adjacent_lead_margin)
    sections: dict[str, list[Item]] = {}
    candidates: list[Item] = []
    for sec in SECTION_ORDER:
        pool = sorted((i for i in usable if i.section == sec and i is not lead), key=_rank, reverse=True)
        limit = settings.section_limits.get(sec, 4)
        chosen = [i for i in pool if i.relevance >= settings.min_relevance][:limit]
        sections[sec] = chosen
        candidates += [i for i in pool if i not in chosen]

    numbers = sorted((i for i in usable if i.section == "market_data" and i.key_number), key=_rank, reverse=True)
    one_number = numbers[0] if numbers else None
    candidates += [i for i in usable if i.section == "market_data" and i is not one_number]
    candidates.sort(key=_rank, reverse=True)

    headline_pool = [lead] + [i for s in SECTION_ORDER for i in sections[s]]
    headline_pool = [i for i in headline_pool if i]
    subject = headline_pool[0].headline if headline_pool else f"{settings.newsletter_name}"
    if len(headline_pool) > 1:
        subject += f", and {headline_pool[1].headline}"  # no lowercasing: headlines start with names
    preview = ("Plus: " + ", ".join(i.headline for i in headline_pool[2:5]) + ".") if len(headline_pool) > 2 else ""

    health = con.execute(
        """
        SELECT source,
               max(fetched_at) FILTER (WHERE status = 'ok')       AS last_ok,
               sum(n_new) FILTER (WHERE fetched_at >= ?)          AS new_this_week,
               arg_max(status, fetched_at)                         AS last_status,
               arg_max(error, fetched_at)                          AS last_error
        FROM feed_runs GROUP BY source ORDER BY source
        """,
        [since],
    ).fetchall()
    con.close()

    return Digest(
        generated_on=today,
        window_start=since.date(),
        window_end=today,
        subject=subject,
        preview=preview,
        lead=lead,
        sections=sections,
        one_number=one_number,
        candidates=candidates,
        skipped=skipped,
        feed_health=health,
        closing_line=settings.closing_line,
        newsletter_name=settings.newsletter_name,
    )


def write(settings: Settings, digest: Digest) -> dict[str, str]:
    issues = settings.docs_dir / "issues"
    issues.mkdir(parents=True, exist_ok=True)
    stem = digest.generated_on.isoformat()
    archive = sorted((p.stem for p in issues.glob("*.html") if p.stem != stem), reverse=True)
    archive = [stem] + archive

    md = render_markdown(digest)
    (issues / f"{stem}.md").write_text(md)
    (issues / f"{stem}.html").write_text(render_html(digest, archive, prefix="../"))
    (settings.docs_dir / "index.html").write_text(render_html(digest, archive, prefix=""))
    (settings.docs_dir / ".nojekyll").write_text("")
    log.info("digest written: docs/index.html and docs/issues/%s.{html,md}", stem)
    return {"html": str(settings.docs_dir / "index.html"), "md": str(issues / f"{stem}.md")}


def run(settings: Settings) -> dict[str, str]:
    return write(settings, build(settings))
