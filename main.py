"""
YouTube → Chessable Course Automator
CLI entry point.

Usage:
  python main.py run <youtube_url>                       # Full pipeline
  python main.py fetch <youtube_url>                     # Stage 1 only
  python main.py review --pgn output/file.pgn            # Stage 2: PGN → Lichess → curated PGN
  python main.py review --lichess-study <url>            # Stage 2: existing study → curated PGN
  python main.py import --pgn output/file_curated.pgn    # Stage 3: curated PGN → Chessable
  python main.py import --pgn ... --course-id <id>       # Stage 3: append to existing course
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
import os
import yaml

load_dotenv()


def load_config() -> dict:
    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        print(f"Error: {key} is not set. Add it to your .env file.", file=sys.stderr)
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_fetch(args, config):
    """Stage 1: YouTube URL → PGN file."""
    from stages.stage1_pgn import run as stage1
    out_path = Path(args.output) if args.output else None
    stage1(args.url, output_path=out_path)


def cmd_review(args, config):
    """Stage 2: PGN / Lichess study → curated PGN."""
    from stages.stage2_lichess import run as stage2
    token = require_env("LICHESS_TOKEN")

    pgn_path = Path(args.pgn) if args.pgn else None
    study_url = args.lichess_study or None
    export_id = args.export_study or None
    out_path = Path(args.output) if args.output else None

    if pgn_path is None and study_url is None and export_id is None:
        print("Error: provide --pgn, --lichess-study, or --export-study", file=sys.stderr)
        sys.exit(1)

    # Derive a study name from the PGN filename or study URL
    if pgn_path:
        study_name = pgn_path.stem.replace("_", " ")
    else:
        study_name = "YouTube Chess Lines"

    stage2(
        token=token,
        pgn_path=pgn_path,
        lichess_study_url=study_url,
        study_name=study_name,
        output_path=out_path,
        export_only_id=export_id,
        orientation=getattr(args, "orientation", None),
    )


def cmd_import(args, config):
    """Stage 3: curated PGN → Chessable course."""
    from stages.stage3_chessable import run as stage3
    username = require_env("CHESSABLE_USERNAME")
    password = require_env("CHESSABLE_PASSWORD")
    piece_color = config.get("default_piece_color", "White")

    pgn_path = Path(args.pgn)
    course_name = pgn_path.stem.replace("_curated", "").replace("_", " ")

    stage3(
        username=username,
        password=password,
        pgn_path=pgn_path,
        course_id=args.course_id or None,
        course_name=course_name,
        piece_color=piece_color,
    )


def cmd_run(args, config):
    """Full pipeline: YouTube URL → Chessable course."""
    from stages.stage1_pgn import run as stage1
    from stages.stage2_lichess import run as stage2
    from stages.stage3_chessable import run as stage3

    token = require_env("LICHESS_TOKEN")
    username = require_env("CHESSABLE_USERNAME")
    password = require_env("CHESSABLE_PASSWORD")
    piece_color = config.get("default_piece_color", "White")

    # Stage 1
    pgn_path = stage1(args.url)

    # Stage 2
    study_name = pgn_path.stem.replace("_", " ")
    orientation = getattr(args, "orientation", None)
    curated_path = stage2(token=token, pgn_path=pgn_path, study_name=study_name, orientation=orientation)

    # Stage 3 — orientation → piece_color (white/black → White/Black)
    if orientation:
        piece_color = orientation.capitalize()
    course_name = pgn_path.stem.replace("_", " ")
    stage3(
        username=username,
        password=password,
        pgn_path=curated_path,
        course_name=course_name,
        piece_color=piece_color,
    )


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="YouTube chess video → Chessable course automator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="Full pipeline: YouTube → Chessable")
    p_run.add_argument("url", help="YouTube video URL")
    p_run.add_argument("--orientation", choices=["white", "black"], help="Board orientation (white or black)")

    # fetch
    p_fetch = sub.add_parser("fetch", help="Stage 1: YouTube → PGN file")
    p_fetch.add_argument("url", help="YouTube video URL")
    p_fetch.add_argument("--output", "-o", help="Output PGN file path (default: output/<title>.pgn)")

    # review
    p_review = sub.add_parser("review", help="Stage 2: PGN / Lichess study → curated PGN")
    p_review.add_argument("--pgn", help="Input PGN file to import into a new Lichess study")
    p_review.add_argument("--lichess-study", metavar="URL", help="Existing Lichess study URL to use as-is")
    p_review.add_argument("--export-study", metavar="STUDY_ID", help="Export & post-process an existing study (skip import)")
    p_review.add_argument("--orientation", choices=["white", "black"], help="Board orientation for all chapters (white or black)")
    p_review.add_argument("--output", "-o", help="Output curated PGN file path")

    # import
    p_import = sub.add_parser("import", help="Stage 3: curated PGN → Chessable course")
    p_import.add_argument("--pgn", required=True, help="Curated PGN file to import")
    p_import.add_argument("--course-id", help="Existing Chessable course ID to append to")

    return parser


def cli():
    config = load_config()
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "run": cmd_run,
        "fetch": cmd_fetch,
        "review": cmd_review,
        "import": cmd_import,
    }
    dispatch[args.command](args, config)


if __name__ == "__main__":
    cli()
