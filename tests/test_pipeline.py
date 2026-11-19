from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import feedparser
import pytest

from vsp import classify, collect, digest
from vsp.config import Settings
from vsp.digest import Item, merge_same_story, pick_lead
from vsp.store import connect
from vsp.text import canonical_url, jaccard, strip_html, title_tokens

FIXTURE = Path(__file__).parent / "fixtures" / "sample_feed.xml"


def _item(**kw) -> Item:
    base = dict(id="x", url="https://e.com", source="src", title="t", published_at=None, tier="core",
                section="money_moves", company="", country="", amount_text="", relevance=5,
                headline="h", one_line="o", summary="s", why_it_matters="w", key_number="",
                leaves_vegan=False)
    base.update(kw)
    return Item(**base)


def test_canonical_url_strips_tracking_and_www():
    assert canonical_url("http://www.Ex.com/a/?utm_source=x&id=3") == "https://ex.com/a?id=3"


def test_title_similarity_ignores_google_news_suffix():
    a = title_tokens("Good Protein secures C$128M to expand dairy-free protein shakes")
    b = title_tokens("Good Protein secures C$128M to expand its dairy-free shakes - FoodBev")
    assert jaccard(a, b) >= collect.DUP_THRESHOLD


def test_adjacent_never_leads_an_equivalent_core_story():
    core = _item(id="c", tier="core", relevance=7)
    adj = _item(id="a", tier="adjacent", relevance=9)
    assert pick_lead([core, adj], min_rel=4, margin=3) is core
    big_adj = _item(id="a2", tier="adjacent", relevance=10)
    assert pick_lead([core, big_adj], min_rel=4, margin=3) is big_adj


def test_merge_same_company_same_section():
    a = _item(id="1", company="Good Protein Inc.", relevance=8, source="vegconomist")
    b = _item(id="2", company="good protein", relevance=6, source="Green Queen", url="https://gq.com")
    merged = merge_same_story([a, b])
    assert len(merged) == 1 and merged[0].id == "1"
    assert ("Green Queen", "https://gq.com") in merged[0].also


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        db_path=tmp_path / "t.duckdb", docs_dir=tmp_path / "docs", fake_llm=True,
        section_limits={"money_moves": 6, "launch_radar": 4, "regulation": 3, "exits_shutdowns": 4},
        closing_line="Know a vegan startup we should cover? Hit reply.",
    )


def _load_fixture(con):
    now = datetime.now(timezone.utc)
    xml = FIXTURE.read_text()
    for i in (1, 2, 3):
        xml = xml.replace(f"{{D{i}}}", format_datetime(now - timedelta(days=i)))
    parsed = feedparser.parse(xml.encode())
    items = [{"url": e.link, "title": e.title, "summary": strip_html(e.get("summary", "")),
              "published_at": datetime(*e.published_parsed[:6])} for e in parsed.entries]
    return collect.insert_items(con, "fixture", items, now.replace(tzinfo=None))


def test_end_to_end_with_fake_llm(settings):
    con = connect(settings.db_path)
    assert _load_fixture(con) == 8
    assert _load_fixture(con) == 0  # idempotent
    dups = con.execute("SELECT count(*) FROM stories WHERE duplicate_of IS NOT NULL").fetchone()[0]
    assert dups == 1  # the Google News copy of Good Protein
    con.execute("INSERT INTO feed_runs VALUES ('fixture', now(), 'ok', 8, 8, NULL)")
    con.close()

    assert classify.run(settings) == 7  # duplicate is not sent to the LLM

    d = digest.build(settings, today=date.today())
    assert d.lead is not None and "Good Protein" in d.lead.headline  # core beats adjacent Oobli
    assert ("fixture", "https://news.google.com/rss/articles/abc123") in d.lead.also
    titles = {i.title for sec in d.sections.values() for i in sec}
    assert not any("cricket" in t.lower() for t in titles)  # off-scope filtered out
    assert any("Daring" in t for t in titles)
    assert any("Veganz" in t for t in titles)
    assert d.one_number and d.one_number.key_number.startswith("$71")

    paths = digest.write(settings, d)
    html = Path(paths["html"]).read_text()
    assert 'id="issue"' in html and "Copy issue for Substack" in html
    assert "<h3>The big one:" in html and "cricket" not in html.split('id="issue"')[1].split("</article>")[0].lower()
    assert Path(paths["md"]).read_text().startswith("# Vegan Startup Weekly")


def test_html_escapes_llm_text(settings):
    d = digest.Digest(
        generated_on=date(2026, 11, 23), window_start=date(2026, 11, 16), window_end=date(2026, 11, 23),
        subject="<script>x</script>", preview="", lead=_item(headline="<b>bad</b>", summary="a & b"),
        sections={}, one_number=None, candidates=[], skipped=[], feed_health=[], closing_line="",
        newsletter_name="VSW",
    )
    from vsp.render import render_html
    out = render_html(d, ["2026-11-23"])
    assert "<script>x</script>" not in out and "&lt;b&gt;bad&lt;/b&gt;" in out
