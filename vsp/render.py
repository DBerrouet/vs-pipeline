"""Render a Digest as a Substack-pasteable HTML page and as Markdown."""
from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .digest import Digest, Item

TITLES = {
    "money_moves": "Money moves",
    "launch_radar": "Launch radar",
    "regulation": "Regulation watch",
    "exits_shutdowns": "Exits and shutdowns",
}


def _a(url: str, text: str) -> str:
    return f'<a href="{escape(url, quote=True)}">{escape(text)}</a>'


def _sources_html(it: "Item") -> str:
    links = [_a(it.url, it.source)] + [_a(u, s) for s, u in it.also[:2]]
    return " · ".join(links)


# ---------------------------------------------------------------- issue body (pasted into Substack)

def issue_html(d: "Digest") -> str:
    out: list[str] = []
    if d.lead:
        L = d.lead
        out.append(f"<h3>The big one: {escape(L.headline)}</h3>")
        out.append(f"<p>{escape(L.summary or L.one_line)} ({_sources_html(L)})</p>")
        if L.why_it_matters:
            out.append(f"<p><strong>Why it matters:</strong> {escape(L.why_it_matters)}</p>")
    for sec, title in TITLES.items():
        items = d.sections.get(sec) or []
        if not items:
            continue
        out.append(f"<h3>{title}</h3><ul>")
        for it in items:
            out.append(
                f"<li><p><strong>{escape(it.label)}:</strong> {escape(it.one_line)} "
                f"({_sources_html(it)})</p></li>"
            )
        out.append("</ul>")
    if d.one_number:
        n = d.one_number
        out.append("<h3>One number</h3>")
        out.append(f"<p><strong>{escape(n.key_number)}</strong> — {escape(n.one_line)} ({_sources_html(n)})</p>")
    if d.closing_line:
        out.append(f"<p>{escape(d.closing_line)}</p>")
    return "\n".join(out)


# ---------------------------------------------------------------- full page

PAGE_CSS = """
:root{--ink:#10261A;--paper:#F6F4EC;--lime:#C8F169;--muted:#5D6F63;--line:#D9DccF}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 Inter,system-ui,-apple-system,Segoe UI,sans-serif}
header{background:var(--ink);color:#F3F1EA;padding:28px 24px}
header .wrap{display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap}
header h1{margin:0;font-size:22px;letter-spacing:-.01em}
header h1 span{color:var(--lime)}
header p{margin:0;color:#A9BBAE;font-size:14px}
.wrap{max-width:780px;margin:0 auto}
main{padding:28px 24px 64px}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin-bottom:20px}
.meta{display:grid;grid-template-columns:110px 1fr auto;gap:10px 12px;align-items:center}
.meta b{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.meta div{font-weight:500}
button{font:600 14px Inter,system-ui,sans-serif;border:0;border-radius:999px;padding:9px 16px;cursor:pointer;background:var(--ink);color:#F3F1EA}
button.primary{background:var(--lime);color:var(--ink);padding:12px 22px;font-size:15px}
button.done{background:#2E7D4F;color:#fff}
.bar{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap}
.bar h2{margin:0;font-size:18px}
.hint{color:var(--muted);font-size:14px;margin:0 0 16px}
#issue{border-top:1px solid var(--line);padding-top:8px}
#issue h3{font-size:19px;margin:22px 0 8px}
#issue ul{padding-left:20px}#issue li p{margin:6px 0}
#issue a{color:#1F6B3F}
h2.sec{font-size:17px;margin:32px 0 10px}
table{width:100%;border-collapse:collapse;font-size:14px;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:#EEF0E6;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;font-size:12px;padding:1px 8px;border-radius:999px;background:#EEF0E6}
.pill.core{background:var(--lime)}.pill.adjacent{background:#D7EEE9}.pill.off_scope{background:#F3D9D2}
.err{color:#A3361F}
details{margin-top:12px}summary{cursor:pointer;font-weight:600}
nav.archive a{margin-right:10px;color:#1F6B3F}
"""

COPY_JS = """
async function copyRich(id, btn){
  const el=document.getElementById(id);
  const html=el.innerHTML, text=el.innerText;
  try{
    await navigator.clipboard.write([new ClipboardItem({
      'text/html':new Blob([html],{type:'text/html'}),
      'text/plain':new Blob([text],{type:'text/plain'})})]);
  }catch(e){
    const r=document.createRange();r.selectNodeContents(el);
    const s=window.getSelection();s.removeAllRanges();s.addRange(r);
    document.execCommand('copy');s.removeAllRanges();
  }
  const old=btn.textContent;btn.textContent='Copied ✓';btn.classList.add('done');
  setTimeout(()=>{btn.textContent=old;btn.classList.remove('done')},1800);
}
"""


def _candidate_rows(items: list["Item"], show_reason: bool = False) -> str:
    rows = []
    for it in items:
        rows.append(
            "<tr>"
            f'<td class="n">{it.relevance}</td>'
            f'<td><span class="pill {escape(it.tier)}">{escape(it.tier)}</span></td>'
            f"<td>{escape(it.section)}</td>"
            f"<td>{_a(it.url, it.title)}<br><small>{escape(it.source)}"
            + (f" — {escape(it.one_line)}" if show_reason and it.one_line else "")
            + "</small></td></tr>"
        )
    return "\n".join(rows)


def render_html(d: "Digest", archive: list[str], prefix: str = "") -> str:
    health_rows = []
    for source, last_ok, new_week, last_status, last_error in d.feed_health:
        status = ('<span class="err">error</span>' if last_status == "error" else "ok")
        detail = escape(last_error or "") if last_status == "error" else ""
        health_rows.append(
            f"<tr><td>{escape(source)}</td><td>{status}</td><td class='n'>{new_week or 0}</td>"
            f"<td>{last_ok.strftime('%d %b %H:%M') if last_ok else '—'}</td><td><small>{detail}</small></td></tr>"
        )
    archive_links = " ".join(
        f'<a href="{prefix}issues/{escape(s)}.html">{escape(s)}</a>' for s in archive[:12]
    )
    md_link = f"{prefix}issues/{d.generated_on.isoformat()}.md"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{escape(d.newsletter_name)} — draft {d.generated_on.isoformat()}</title>
<style>{PAGE_CSS}</style></head>
<body>
<header><div class="wrap">
  <h1>Vegan Startup<span>.</span> draft</h1>
  <p>Stories from {d.window_start:%d %b} to {d.window_end:%d %b %Y} · generated {d.generated_on:%A %d %B}</p>
</div></header>
<main class="wrap">

<div class="card meta">
  <b>Subject</b><div id="subject">{escape(d.subject)}</div><button onclick="copyRich('subject',this)">Copy</button>
  <b>Preview</b><div id="preview">{escape(d.preview)}</div><button onclick="copyRich('preview',this)">Copy</button>
</div>

<div class="card">
  <div class="bar"><h2>Issue draft</h2><button class="primary" onclick="copyRich('issue',this)">Copy issue for Substack</button></div>
  <p class="hint">Click the button, then paste into a new Substack post (Cmd/Ctrl+V). Headings, bold text and links carry over.
  Add your intro line, check each story against its source, and swap items from the candidates below if needed.</p>
  <article id="issue">
{issue_html(d)}
  </article>
</div>

<h2 class="sec">Other candidates ({len(d.candidates)})</h2>
<p class="hint">In scope but not in the draft: over the section limit or below the relevance cut-off.</p>
<table><tr><th>Score</th><th>Tier</th><th>Section</th><th>Story</th></tr>
{_candidate_rows(d.candidates, show_reason=True) or '<tr><td colspan="4">None this week.</td></tr>'}
</table>

<details><summary>Skipped or off-scope ({len(d.skipped)})</summary>
<p class="hint">Check now and then that nothing vegan was filtered out by mistake.</p>
<table><tr><th>Score</th><th>Tier</th><th>Section</th><th>Story</th></tr>
{_candidate_rows(d.skipped) or '<tr><td colspan="4">None.</td></tr>'}
</table></details>

<h2 class="sec">Feed health</h2>
<table><tr><th>Feed</th><th>Last run</th><th>New (7 d)</th><th>Last OK</th><th>Error</th></tr>
{''.join(health_rows) or '<tr><td colspan="5">No runs yet.</td></tr>'}
</table>

<p class="hint" style="margin-top:28px"><a href="{md_link}">Markdown version</a></p>
<nav class="archive hint">Past drafts: {archive_links}</nav>
</main>
<script>{COPY_JS}</script>
</body></html>
"""


# ---------------------------------------------------------------- markdown

def _md_sources(it: "Item") -> str:
    return " · ".join([f"[{it.source}]({it.url})"] + [f"[{s}]({u})" for s, u in it.also[:2]])


def render_markdown(d: "Digest") -> str:
    lines = [
        f"# {d.newsletter_name} — draft {d.generated_on.isoformat()}",
        "",
        f"**Subject:** {d.subject}  ",
        f"**Preview:** {d.preview}",
        "",
    ]
    if d.lead:
        L = d.lead
        lines += [f"### The big one: {L.headline}", "", f"{L.summary or L.one_line} ({_md_sources(L)})", ""]
        if L.why_it_matters:
            lines += [f"**Why it matters:** {L.why_it_matters}", ""]
    for sec, title in TITLES.items():
        items = d.sections.get(sec) or []
        if items:
            lines += [f"### {title}", ""]
            lines += [f"- **{it.label}:** {it.one_line} ({_md_sources(it)})" for it in items]
            lines.append("")
    if d.one_number:
        n = d.one_number
        lines += ["### One number", "", f"**{n.key_number}** — {n.one_line} ({_md_sources(n)})", ""]
    if d.closing_line:
        lines += [d.closing_line, ""]
    lines += ["---", "", f"## Other candidates ({len(d.candidates)})", ""]
    lines += [f"- [{c.relevance}] {c.tier}/{c.section} — [{c.title}]({c.url}) ({c.source})" for c in d.candidates]
    return "\n".join(lines) + "\n"
