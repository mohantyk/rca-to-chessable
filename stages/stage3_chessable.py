"""
Stage 3 — Chessable Import
Curated PGN → private Chessable course chapter.

Uses the chessable-import library (kamui-fin/chessable-import) which drives
the Chessable web UI via Selenium. Requires Chrome + ChromeDriver installed.
"""

import sys
from pathlib import Path

# chessable-import exposes a ChessableImporter class
try:
    from chessable_import import ChessableImporter
except ImportError:
    print(
        "[Stage 3] chessable-import is not installed.\n"
        "  Run: uv add chessable-import",
        file=sys.stderr,
    )
    sys.exit(1)


def list_courses(importer: "ChessableImporter") -> list[dict]:
    """Return the user's existing Chessable courses."""
    try:
        return importer.get_courses()
    except Exception as exc:
        print(f"[Stage 3] Could not fetch courses: {exc}", file=sys.stderr)
        return []


def pick_or_create_course(importer: "ChessableImporter", suggested_name: str, piece_color: str) -> str:
    """
    Interactively ask the user whether to create a new course or append to existing.
    Returns the course ID to import into.
    """
    courses = list_courses(importer)

    print("\n[Stage 3] Your Chessable courses:")
    if courses:
        for i, c in enumerate(courses, start=1):
            print(f"  [{i}] {c['name']} (id: {c['id']})")
    else:
        print("  (none found)")

    print(f"  [N] Create new course: '{suggested_name}'")
    choice = input("  Enter number to append, or N to create new [N]: ").strip()

    if choice.lower() in ("", "n"):
        print(f"[Stage 3] Creating new course '{suggested_name}'…")
        course_id = importer.create_course(
            name=suggested_name,
            course_type="opening",
            color=piece_color.lower(),
        )
        print(f"  Created course ID: {course_id}")
        return course_id

    try:
        idx = int(choice) - 1
        return courses[idx]["id"]
    except (ValueError, IndexError):
        print("  Invalid selection — creating new course.")
        return importer.create_course(
            name=suggested_name,
            course_type="opening",
            color=piece_color.lower(),
        )


def run(
    username: str,
    password: str,
    pgn_path: Path,
    course_id: str | None = None,
    course_name: str = "YouTube Chess Course",
    piece_color: str = "White",
) -> None:
    """
    Full Stage 3 run.  If course_id is provided, imports directly into that
    course without prompting.
    """
    if not pgn_path.exists():
        print(f"[Stage 3] PGN file not found: {pgn_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[Stage 3] Logging into Chessable as {username}…")
    try:
        importer = ChessableImporter(username=username, password=password)
        importer.login()
    except Exception as exc:
        print(f"[Stage 3] Login failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if course_id is None:
        course_id = pick_or_create_course(importer, course_name, piece_color)

    print(f"[Stage 3] Importing {pgn_path} into course {course_id}…")
    try:
        importer.import_pgn(
            pgn_path=str(pgn_path),
            course_id=course_id,
            import_variations=True,   # "Import all sub-variations as their own item"
            auto_key_moves=False,     # honour our {[%key]} annotations
        )
    except Exception as exc:
        print(f"[Stage 3] Import failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\n[Stage 3] Done. Course ready to drill:")
    print(f"  https://www.chessable.com/course/{course_id}/")
