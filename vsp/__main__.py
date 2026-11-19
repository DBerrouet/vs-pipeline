"""CLI:  python -m vsp {collect|classify|digest|all} [options]"""
from __future__ import annotations

import argparse
import logging

from . import classify, collect, digest
from .config import load_settings


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="vsp", description="Vegan Startup Weekly curation pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("collect", help="fetch feeds and store new stories")
    c = sub.add_parser("classify", help="classify unclassified stories with Claude")
    c.add_argument("--reclassify", action="store_true", help="re-run every recent story with the current prompt")
    c.add_argument("--limit", type=int, help="classify at most N stories (for testing)")
    sub.add_parser("digest", help="build the issue draft in docs/")
    sub.add_parser("all", help="collect + classify + digest")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    s = load_settings()
    if args.cmd in ("collect", "all"):
        collect.run(s)
    if args.cmd in ("classify", "all"):
        classify.run(s, reclassify=getattr(args, "reclassify", False), limit=getattr(args, "limit", None))
    if args.cmd in ("digest", "all"):
        digest.run(s)


if __name__ == "__main__":
    main()
