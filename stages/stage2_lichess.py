"""
Stage 2 — Lichess Review
PGN file (or existing Lichess study URL) → curated PGN with key moves flagged.

Flow:
  1. Create a private Lichess study from the PGN
  2. Open the study URL in the browser
  3. User curates lines, sets depth, annotates with '!'
  4. User presses Enter to signal completion
  5. Export the study PGN via API
  6. Post-process: map '!' → {[%key]}, validate
  7. Write curated PGN to output/
"""

import re
import sys
import webbrowser
from pathlib import Path

import requests

from utils.pgn_utils import map_annotations_to_key_moves, validate_pgn

OUTPUT_DIR = Path("output")
LICHESS_API = "https://lichess.org/api"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def create_study(token: str, name: str) -> str:
    """Create a new private Lichess study. Returns the study ID."""
    resp = requests.post(
        f"{LICHESS_API}/study",
        headers=_headers(token),
        json={
            "name": name,
            "visibility": "unlisted",
            "explorer": "nobody",
            "computer": "nobody",
            "chat": "nobody",
            "shareable": "member",
            "cloneable": "nobody",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"[Stage 2] Failed to create study: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    study_id = resp.json()["id"]
    print(f"[Stage 2] Created study '{name}' — ID: {study_id}")
    return study_id


def prompt_orientation() -> str:
    """Ask the user which side the opening is for. Returns 'white' or 'black'."""
    print("\n[Stage 2] Which side is this opening for?")
    print("  [w] White")
    print("  [b] Black")
    choice = input("  Choice [w/b]: ").strip().lower()
    return "black" if choice == "b" else "white"


def import_pgn_to_study(token: str, study_id: str, pgn_text: str, chapter_name: str = "Lines", orientation: str = "white") -> None:
    """Import a PGN string as a chapter into an existing study."""
    resp = requests.post(
        f"{LICHESS_API}/study/{study_id}/import-pgn",
        headers={**_headers(token), "Content-Type": "application/x-www-form-urlencoded"},
        data={"pgn": pgn_text, "name": chapter_name, "orientation": orientation},
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        print(f"[Stage 2] PGN import failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    print(f"[Stage 2] Imported PGN as chapter '{chapter_name}'.")


def export_study_pgn(token: str, study_id: str) -> str:
    """Export the full study as a PGN string via the Lichess API."""
    resp = requests.get(
        f"{LICHESS_API}/study/{study_id}.pgn",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code == 403:
        print(
            f"[Stage 2] Export failed — study is private.\n"
            f"  In Lichess: open the study → gear icon → set Visibility to 'Unlisted' → save.\n"
            f"  New studies created by this tool are already set to Unlisted.",
            file=sys.stderr,
        )
        sys.exit(1)
    if resp.status_code != 200:
        print(f"[Stage 2] Export failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.text


def study_id_from_url(url: str) -> str | None:
    """Extract study ID from a Lichess study URL like https://lichess.org/study/abc12345."""
    match = re.search(r'lichess\.org/study/([A-Za-z0-9]{8})', url)
    return match.group(1) if match else None


def export_and_process(
    token: str,
    study_id: str,
    study_name: str = "YouTube Chess Lines",
    output_path: Path | None = None,
) -> Path:
    """
    Export an existing Lichess study and post-process it (map ! → {[%key]}).
    Use this after you've finished curating in the browser.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"[Stage 2] Exporting study {study_id}…")
    exported_pgn = export_study_pgn(token, study_id)
    curated_pgn = map_annotations_to_key_moves(exported_pgn)

    games, errors = validate_pgn(curated_pgn)
    if errors:
        print(f"  Warning: {len(errors)} validation issue(s) in exported PGN:")
        for err in errors:
            print(f"    - {err}")

    if output_path is None:
        safe_name = re.sub(r'[^\w\s-]', '', study_name).strip().replace(' ', '_')[:60]
        output_path = OUTPUT_DIR / f"{safe_name}_curated.pgn"

    output_path.write_text(curated_pgn)
    print(f"\n[Stage 2] Done. Curated PGN written to {output_path}")
    return output_path


def run(
    token: str,
    pgn_path: Path | None = None,
    lichess_study_url: str | None = None,
    study_name: str = "YouTube Chess Lines",
    output_path: Path | None = None,
    export_only_id: str | None = None,
    orientation: str | None = None,
) -> Path:
    """
    Full Stage 2 run.  Supply either pgn_path (creates a new study) or
    lichess_study_url (uses an existing study, skipping import).
    Returns path to the curated output PGN file.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Skip straight to export if caller already has a study ID
    if export_only_id:
        return export_and_process(token, export_only_id, study_name, output_path)

    if lichess_study_url:
        # Use existing study — skip creation and import
        study_id = study_id_from_url(lichess_study_url)
        if not study_id:
            print(f"[Stage 2] Could not parse study ID from URL: {lichess_study_url}", file=sys.stderr)
            sys.exit(1)
        print(f"[Stage 2] Using existing study: {study_id}")
        study_url = lichess_study_url
    else:
        if pgn_path is None or not pgn_path.exists():
            print("[Stage 2] No PGN file provided.", file=sys.stderr)
            sys.exit(1)

        pgn_text = pgn_path.read_text()

        if orientation is None:
            orientation = prompt_orientation()

        study_id = create_study(token, study_name)

        # Split multi-game PGN into chapters (one chapter per game)
        # Simple heuristic: split on double-newline before [Event
        chapters = re.split(r'\n\n(?=\[Event)', pgn_text)
        for i, chapter_pgn in enumerate(chapters, start=1):
            chapter_pgn = chapter_pgn.strip()
            if not chapter_pgn:
                continue
            # Try to derive a chapter name from the White/Black headers
            white = re.search(r'\[White "([^"]+)"\]', chapter_pgn)
            black = re.search(r'\[Black "([^"]+)"\]', chapter_pgn)
            if white and black:
                chapter_name = f"{white.group(1)} vs {black.group(1)}"
            else:
                chapter_name = f"Line {i}"
            import_pgn_to_study(token, study_id, chapter_pgn, chapter_name, orientation)

        study_url = f"https://lichess.org/study/{study_id}"

    print(f"\n[Stage 2] Study URL: {study_url}")
    print("  Opening in your browser…")
    webbrowser.open(study_url)

    print("\n  Review your lines in Lichess:")
    print("  - Delete lines/chapters you don't want")
    print("  - Trim lines at the depth you want to memorise")
    print("  - Annotate key moves with '!' (the '!' button in the annotation panel)")
    print("\n  Press Enter when you're done curating…")
    input()

    print("[Stage 2] Exporting study…")
    exported_pgn = export_study_pgn(token, study_id)

    # Post-process: map ! (NAG $1) → {[%key]}
    curated_pgn = map_annotations_to_key_moves(exported_pgn)

    # Validate
    games, errors = validate_pgn(curated_pgn)
    if errors:
        print(f"  Warning: {len(errors)} validation issue(s) in exported PGN:")
        for err in errors:
            print(f"    - {err}")

    if output_path is None:
        safe_name = re.sub(r'[^\w\s-]', '', study_name).strip().replace(' ', '_')[:60]
        output_path = OUTPUT_DIR / f"{safe_name}_curated.pgn"

    output_path.write_text(curated_pgn)
    print(f"\n[Stage 2] Done. Curated PGN written to {output_path}")
    return output_path
