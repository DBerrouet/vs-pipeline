# Vegan Startup Weekly — curation pipeline

RSS → dedupe → Claude classification → ranked issue draft you paste into Substack.

```
feeds.yaml ──collect──▶ stories ──classify (Claude)──▶ classifications ──digest──▶ docs/index.html
  (daily)              (DuckDB)   tier · section · score   (DuckDB)      (Monday)   "Copy issue for Substack"
```

- **Every day, 05:17 UTC:** fetch all feeds, store new stories, skip near-duplicate titles, then classify only the new ones.
- **Monday, 05:41 Paris time:** same, then build the draft for the week.
- **Monday morning, you:** open the Pages URL, click **Copy issue for Substack**, paste into a new post, write the intro, check each story against its source.

## What the classifier applies

Your editorial policy is in the prompt (`vsp/classify.py`):

| Tier | Meaning | In the draft |
|---|---|---|
| `core` | brand classifies its products as vegan | prioritised; always wins the lead at equal score |
| `adjacent` | animal-free tech (precision fermentation, cultivated meat…) | included; leads only if it scores 3+ points above the best core story (`adjacent_lead_margin`) |
| `off_scope` | animal products, hybrids, generic food-tech | dropped, except "company stops being all-vegan" news, which goes to Exits and shutdowns in a neutral tone |

Each story gets a section (Money moves, Launch radar, Regulation watch, Exits and shutdowns, One number, or skip), a 0–10 relevance score, and a one-line summary written in its own words with amounts as "original currency (about US$…)".

The draft page also shows **Other candidates** (in scope but cut), **Skipped or off-scope** (glance at it now and then for false negatives), and **Feed health**.

## Setup (about 10 minutes)

1. **Create a GitHub repo** (public, so Pages is free; see the privacy note below) and push this folder:
   ```bash
   git init && git add . && git commit -m "curation pipeline"
   git branch -M main
   git remote add origin git@github.com:<you>/vegan-startup-pipeline.git
   git push -u origin main
   ```
2. **Add your API key:** repo → Settings → Secrets and variables → Actions → New repository secret → `ANTHROPIC_API_KEY`.
3. **Turn on Pages:** Settings → Pages → Source: *Deploy from a branch* → `main` / `/docs`.
4. **First run:** Actions tab → *curation* → *Run workflow* (leave "Also build the digest" ticked). After about 2 minutes the draft is at `https://<you>.github.io/vegan-startup-pipeline/`.
5. Open the page and check **Feed health**. Disable any feed that errors in `feeds.yaml`. The PlantBase Mag URL is a guess based on the site running on Wix.

The first run only covers what the feeds hold right now, often just a few days. The draft is complete from the second Monday on.

## Privacy note

GitHub Pages on a free account is public: the draft is readable by anyone who knows the URL, a day before you send. The page is marked `noindex`. If that matters, make the repo private and either use GitHub Pro (private Pages) or skip Pages and open `docs/index.html` from the repo's files instead.

## Cost

About 100–200 new stories a week × one Haiku call each (about 1,000 input + 300 output tokens) comes to a few cents a week. Set `VSP_MODEL` or `model:` in `config.yaml` to use a larger model.

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python -m vsp all                 # collect + classify + digest
open docs/index.html

VSP_FAKE_LLM=1 python -m vsp all  # dry run with keyword rules, no API calls
python -m vsp classify --limit 5  # try the prompt on a few stories
python -m pytest -q
```

Query the history directly:

```bash
duckdb data/vsp.duckdb "select c.relevance, c.tier, c.section, s.title
  from stories s join classifications c on c.story_id = s.id
  order by s.published_at desc limit 20"
```

## Tuning

- **Sources:** `feeds.yaml`. Any RSS/Atom URL works, including Google News search feeds.
- **Thresholds and section sizes:** `config.yaml`.
- **Editorial rules:** `SYSTEM_PROMPT` in `vsp/classify.py`. Bump `PROMPT_VERSION` and run `python -m vsp classify --reclassify` to re-score the last 10 days with the new rules.

## Layout

```
vsp/collect.py    fetch feeds, canonical URLs, title-similarity dedupe, feed health log
vsp/classify.py   Claude tool-use call with the editorial policy; FakeClassifier for tests
vsp/digest.py     merge same-company stories, pick the lead, fill sections
vsp/render.py     Substack-pasteable HTML (copy button) + Markdown
vsp/store.py      DuckDB schema: stories, classifications, feed_runs
data/vsp.duckdb   story history, committed back by the workflow
docs/             GitHub Pages: index.html = latest draft, issues/ = archive
```
