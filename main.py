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
    pgn_path, title = stage1(args.url, output_path=out_path)
    print(f"[fetch] Video title: {title}")


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
    orientation = getattr(args, "orientation", None)
    piece_color = orientation.capitalize() if orientation else config.get("default_piece_color", "White")
    pgn_path = Path(args.pgn)
    manual = getattr(args, "manual", False)

    if manual:
        stage3(pgn_path=pgn_path, manual=True)
        return

    email = require_env("CHESSABLE_EMAIL")
    password = require_env("CHESSABLE_PASSWORD")

    # Chapter mode: --new-chapter <name> creates it; --chapter <name> uses existing
    new_chapter_name = getattr(args, "new_chapter", None)
    existing_chapter = getattr(args, "chapter", None)
    if new_chapter_name and existing_chapter:
        print("Error: use --chapter OR --new-chapter, not both.", file=sys.stderr)
        sys.exit(1)
    if not new_chapter_name and not existing_chapter:
        print("Error: --auto requires either --chapter <name> or --new-chapter <name>.", file=sys.stderr)
        sys.exit(1)

    chapter_name = new_chapter_name or existing_chapter
    new_chapter = bool(new_chapter_name)

    # Course targeting: exactly one of --new-course or --course-id must be given
    new_course   = getattr(args, "new_course", False)
    course_id_str = getattr(args, "course_id", None)

    if new_course and course_id_str:
        print("Error: use --new-course OR --course-id, not both.", file=sys.stderr)
        sys.exit(1)
    if not new_course and not course_id_str:
        print("Error: specify --new-course (create) or --course-id <id> (existing).", file=sys.stderr)
        sys.exit(1)

    course_id = None if new_course else int(course_id_str)

    course_name = getattr(args, "course_name", None) or pgn_path.stem.replace("_curated", "").replace("_", " ")
    if new_course and not getattr(args, "course_name", None):
        print("Error: --new-course requires --course-name <name>.", file=sys.stderr)
        sys.exit(1)

    stage3(
        pgn_path=pgn_path,
        manual=False,
        email=email,
        password=password,
        course_name=course_name,
        chapter_name=chapter_name,
        new_chapter=new_chapter,
        piece_color=piece_color,
        course_id=course_id,
    )


def cmd_run(args, config):
    """Full pipeline: YouTube URL → Chessable course."""
    from stages.stage1_pgn import run as stage1
    from stages.stage2_lichess import run as stage2
    from stages.stage3_chessable import run as stage3

    token = require_env("LICHESS_TOKEN")
    email = require_env("CHESSABLE_EMAIL")
    password = require_env("CHESSABLE_PASSWORD")
    piece_color = config.get("default_piece_color", "White")

    # Stage 1 — returns (pgn_path, video_title)
    pgn_path, video_title = stage1(args.url)

    # Stage 2 — user curates in Lichess, then this exports the curated PGN
    orientation = getattr(args, "orientation", None)
    curated_path = stage2(token=token, pgn_path=pgn_path, study_name=video_title, orientation=orientation)

    # Stage 3 — one chapter per video, named after the video title
    if orientation:
        piece_color = orientation.capitalize()
    course_name = config.get("course_name", video_title)
    stage3(
        email=email,
        password=password,
        pgn_path=curated_path,
        course_name=course_name,
        chapter_name=video_title,   # video title becomes the chapter name
        new_chapter=True,           # full pipeline always creates a fresh chapter
        piece_color=piece_color,
        manual=False,
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
    p_import.add_argument("--manual", action="store_true", help="Copy PGN to clipboard and open browser manually (default: Playwright automation)")
    p_import.add_argument("--new-course", action="store_true", dest="new_course", help="Create a brand-new Chessable course")
    p_import.add_argument("--course-id", required=False, help="ID of an existing Chessable course (bid= from bookadmin URL)")
    p_import.add_argument("--course-name", required=False, help="Course display name — required with --new-course; must match exactly with --course-id")
    p_import.add_argument("--orientation", choices=["white", "black"], help="Piece color when creating a new course (white or black)")
    p_import.add_argument("--chapter", metavar="CHAPTER_NAME", help="Import into this existing chapter (default mode)")
    p_import.add_argument("--new-chapter", metavar="CHAPTER_NAME", dest="new_chapter", help="Create this chapter, then import into it")

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
