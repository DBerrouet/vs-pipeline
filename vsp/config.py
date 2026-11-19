from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Feed:
    name: str
    url: str
    enabled: bool = True


@dataclass
class Settings:
    model: str = "claude-haiku-5-5"
    classify_max_age_days: int = 10
    digest_lookback_days: int = 7
    min_relevance: int = 4
    adjacent_lead_margin: int = 3
    section_limits: dict[str, int] = field(default_factory=dict)
    newsletter_name: str = "Vegan Startup Weekly"
    closing_line: str = ""
    fake_llm: bool = False
    db_path: Path = ROOT / "data" / "vsp.duckdb"
    docs_dir: Path = ROOT / "docs"
    feeds: list[Feed] = field(default_factory=list)


def load_settings(root: Path = ROOT) -> Settings:
    cfg = yaml.safe_load((root / "config.yaml").read_text()) or {}
    feeds_cfg = yaml.safe_load((root / "feeds.yaml").read_text()) or {}
    s = Settings(**{k: v for k, v in cfg.items() if k in Settings.__dataclass_fields__})
    s.feeds = [Feed(**f) for f in feeds_cfg.get("feeds", [])]
    s.model = os.environ.get("VSP_MODEL", s.model)
    s.fake_llm = os.environ.get("VSP_FAKE_LLM", "") not in ("", "0", "false")
    if os.environ.get("VSP_DB"):
        s.db_path = Path(os.environ["VSP_DB"])
    if os.environ.get("VSP_DOCS"):
        s.docs_dir = Path(os.environ["VSP_DOCS"])
    return s
