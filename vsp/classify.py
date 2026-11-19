"""Classify each new story with Claude: tier, section, relevance and a summary in our own words."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from .config import Settings
from .store import connect

log = logging.getLogger(__name__)

# Bump when the prompt changes so old stories can be re-classified on purpose
# (`python -m vsp classify --reclassify`).
PROMPT_VERSION = "2026-11-19.1"

SYSTEM_PROMPT = """\
You are the curation assistant for Vegan Startup Weekly, an English-language newsletter \
and Instagram account (@vegan.startup) covering vegan startup and business news worldwide: \
who raised, who launched, who closed, and why it matters.

EDITORIAL POLICY — apply it strictly.
- core: the company's products are classified as vegan by the brand (plant-based food and \
drink brands, vegan cosmetics, vegan fashion/materials, vegan retailers). Always prioritised.
- adjacent: animal-free technology that can benefit animals without being a vegan consumer \
brand: precision fermentation, animal-free dairy/egg proteins, cultivated meat, biomass \
fermentation, ingredient suppliers (e.g. Oobli, Amyris, Solar Foods). Covered when it \
matters to the vegan economy; never leads over an equivalent core story.
- off_scope: anything selling or containing animal products (meat, dairy, eggs, insects, \
honey, leather), hybrid products, generic food-tech or agtech, generic VC news. \
EXCEPTION: when a company we would cover stops being all-vegan (e.g. "HappyVore launches \
a vegetarian product"), set leaves_vegan=true, tier=core, section=exits_shutdowns, and \
write it in a neutral, factual tone without promoting the new product.
- If you cannot tell whether a brand is vegan, say so in one_line ("vegan status unclear") \
and lower relevance by 2.

SECTIONS
- money_moves: funding rounds, acquisitions, mergers, IPOs, grants, accelerator selections.
- launch_radar: new products, retail listings, restaurant openings, market entries.
- regulation: approvals, labelling rules, taxes, bans, policy.
- exits_shutdowns: insolvencies, closures, layoffs, discontinued brands, leaving vegan.
- market_data: reports and figures about the market (sales, funding totals, surveys).
- skip: opinion pieces, recipes, events listings, roundups of other news, off-scope stories.

RELEVANCE (0–10) for our readers (founders, investors, vegan-industry people):
9–10 large round (> US$50M), major acquisition/insolvency of a known vegan brand, landmark regulation.
6–8 notable round (US$5–50M), significant launch by a known brand, useful market figure.
3–5 small round, minor launch, regional news.
0–2 off-scope, skip, or barely related.
Off-scope stories (without leaves_vegan) must score 0–1.

WRITING RULES
- Write in your own words. Never copy a sentence or distinctive phrase from the source; \
names, numbers and product names are fine.
- Amounts: original currency first, then USD equivalent, e.g. "€12M (about US$13M)".
- one_line: ≤ 30 words, no company name at the start (it is shown before the line), \
e.g. "raised €12M (about US$13M) led by X to expand its oat-based cheese into Germany."
- summary: 2–3 sentences, factual, for when the story leads the issue.
- why_it_matters: 1–2 sentences of analysis for vegan founders and investors.
- headline: ≤ 12 words, newsletter style, e.g. "Good Protein secures C$128M".
- key_number: only for market_data, a single figure like "$71M"; otherwise empty.
Use only facts present in the title and text you are given; do not invent investors, \
amounts or dates. Record your answer with the record_story tool."""

TOOL = {
    "name": "record_story",
    "description": "Record the classification of one news story.",
    "input_schema": {
        "type": "object",
        "properties": {
            "tier": {"type": "string", "enum": ["core", "adjacent", "off_scope"]},
            "section": {
                "type": "string",
                "enum": ["money_moves", "launch_radar", "regulation", "exits_shutdowns", "market_data", "skip"],
            },
            "company": {"type": "string", "description": "Main company name, or empty."},
            "country": {"type": "string", "description": "Company's country, or empty."},
            "amount_text": {"type": "string", "description": "Deal amount as written, e.g. '€12M (about US$13M)', or empty."},
            "relevance": {"type": "integer", "minimum": 0, "maximum": 10},
            "headline": {"type": "string"},
            "one_line": {"type": "string"},
            "summary": {"type": "string"},
            "why_it_matters": {"type": "string"},
            "key_number": {"type": "string"},
            "leaves_vegan": {"type": "boolean"},
        },
        "required": ["tier", "section", "company", "country", "amount_text", "relevance",
                     "headline", "one_line", "summary", "why_it_matters", "key_number", "leaves_vegan"],
    },
}

FIELDS = TOOL["input_schema"]["required"]


def _user_message(title: str, summary: str, source: str, published) -> str:
    return (f"Source: {source}\nPublished: {published or 'unknown'}\n"
            f"Title: {title}\n\nText:\n{summary or '(no text in feed)'}")


class ClaudeClassifier:
    def __init__(self, model: str):
        import anthropic

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set (or use VSP_FAKE_LLM=1 for a dry run).")
        self.client = anthropic.Anthropic(max_retries=4)
        self.model = model

    def __call__(self, title, summary, source, published) -> dict:
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=800,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "record_story"},
            messages=[{"role": "user", "content": _user_message(title, summary, source, published)}],
        )
        block = next(b for b in msg.content if b.type == "tool_use")
        return block.input


class FakeClassifier:
    """Keyword rules, no API calls. For tests and dry runs only."""

    model = "fake"
    _AMOUNT = re.compile(r"([$€£]|C\$|US\$)\s?\d[\d.,]*\s?(M|million|bn|billion|k)?", re.I)

    def __call__(self, title, summary, source, published) -> dict:
        t = f"{title} {summary}".lower()
        off = any(w in t for w in ("insect", "cricket", "beef cattle", "dairy farm", "chicken farm"))
        adjacent = any(w in t for w in ("fermentation", "cultivated", "cell-based", "precision"))
        if any(w in t for w in ("raise", "funding", "seed", "series", "acquir", "invest")):
            section = "money_moves"
        elif any(w in t for w in ("insolven", "shut", "closes", "bankrupt", "layoff")):
            section = "exits_shutdowns"
        elif any(w in t for w in ("approv", "regulat", "vat", "label", "efsa", "novel food")):
            section = "regulation"
        elif any(w in t for w in ("launch", "debut", "rolls out", "opens")):
            section = "launch_radar"
        elif any(w in t for w in ("report", "survey", "market", "sales")):
            section = "market_data"
        else:
            section = "skip"
        m = self._AMOUNT.search(f"{title} {summary}")
        rel = 0 if off else (7 if m else 5) - (1 if adjacent else 0)
        if section == "skip":
            rel = min(rel, 2)
        company = title.split(" ")[0].strip(",:’'s")
        return {
            "tier": "off_scope" if off else ("adjacent" if adjacent else "core"),
            "section": "skip" if off else section,
            "company": company,
            "country": "",
            "amount_text": m.group(0) if m else "",
            "relevance": rel,
            "headline": title[:80],
            "one_line": (summary or title)[:160],
            "summary": (summary or title)[:300],
            "why_it_matters": "(dry run — no analysis)",
            "key_number": m.group(0) if (m and section == "market_data") else "",
            "leaves_vegan": False,
        }


def make_classifier(settings: Settings):
    return FakeClassifier() if settings.fake_llm else ClaudeClassifier(settings.model)


def run(settings: Settings, reclassify: bool = False, limit: int | None = None, classifier=None) -> int:
    con = connect(settings.db_path)
    classifier = classifier or make_classifier(settings)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=settings.classify_max_age_days)
    version_filter = "c.prompt_version = ?" if not reclassify else "FALSE"
    params = [PROMPT_VERSION] if not reclassify else []
    rows = con.execute(
        f"""
        SELECT s.id, s.title, s.summary, s.source, s.published_at
        FROM stories s
        LEFT JOIN classifications c ON c.story_id = s.id AND {version_filter}
        WHERE c.story_id IS NULL
          AND s.duplicate_of IS NULL
          AND coalesce(s.published_at, s.fetched_at) >= ?
        ORDER BY coalesce(s.published_at, s.fetched_at) DESC
        """,
        params + [cutoff],
    ).fetchall()
    if limit:
        rows = rows[:limit]

    done = 0
    for sid, title, summary, source, published in rows:
        try:
            out = classifier(title, summary, source, published)
        except Exception as exc:
            log.warning("classify failed for %s: %s", title[:60], exc)
            continue
        values = [out.get(f) for f in FIELDS]
        con.execute("DELETE FROM classifications WHERE story_id = ?", [sid])
        con.execute(
            f"INSERT INTO classifications (story_id, model, prompt_version, {', '.join(FIELDS)}, classified_at) "
            f"VALUES (?, ?, ?, {', '.join('?' * len(FIELDS))}, now())",
            [sid, classifier.model, PROMPT_VERSION, *values],
        )
        done += 1
        log.info("[%s/%s r=%s] %s", out.get("tier"), out.get("section"), out.get("relevance"), title[:70])
    con.close()
    log.info("classified %d stories", done)
    return done


if __name__ == "__main__":  # handy for eyeballing the tool schema
    print(json.dumps(TOOL, indent=2))
