"""
Stage 1 — PGN Acquisition
YouTube URL → validated .pgn file in output/

Primary path: yt-dlp fetches the video description, we look for external URLs,
scrape those pages for PGN blocks, validate with python-chess.

Fallback (Phase 2): transcript extraction via LLM — not implemented here.
"""

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from utils.pgn_utils import extract_pgn_blocks, extract_pgn_from_scripts, validate_pgn, games_to_pgn

OUTPUT_DIR = Path("output")
_URL_RE = re.compile(r'https?://[^\s\)\]>\"\']+')


def fetch_video_info(youtube_url: str) -> dict:
    """Use yt-dlp to fetch the video title and description (no download)."""
    print(f"[Stage 1] Fetching video info for: {youtube_url}")
    result = subprocess.run(
        [
            "yt-dlp",
            "--skip-download",
            "--print", "%(title)s",
            "--print", "%(description)s",
            youtube_url,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  yt-dlp error:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    lines = result.stdout.split("\n", 1)
    title = lines[0].strip()
    description = lines[1].strip() if len(lines) > 1 else ""
    print(f"  Title: {title}")
    return {"title": title, "description": description}


def find_urls_in_text(text: str) -> list[str]:
    """Extract all HTTP(S) URLs from a block of text."""
    return _URL_RE.findall(text)


def scrape_pgn_from_url(url: str) -> list[str]:
    """
    Fetch a URL and return any PGN blocks found in the page.
    Handles both raw PGN pages and HTML pages with embedded PGN.
    """
    print(f"  Scraping: {url}")
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"    Warning: could not fetch {url}: {exc}")
        return []

    content_type = resp.headers.get("Content-Type", "")

    # Raw PGN file served directly
    if "text/plain" in content_type or url.endswith(".pgn"):
        return extract_pgn_blocks(resp.text)

    # HTML page
    soup = BeautifulSoup(resp.text, "html.parser")

    found = []

    # 1. JavaScript-embedded PGN (e.g. RPBChessboard.renderPGN on chess-teacher.com)
    found.extend(extract_pgn_from_scripts(resp.text))
    if found:
        return found

    # 2. <pre> and <code> tags
    for tag in soup.find_all(["pre", "code"]):
        found.extend(extract_pgn_blocks(tag.get_text()))
    if found:
        return found

    # 3. Full page plain text fallback
    found.extend(extract_pgn_blocks(soup.get_text(separator="\n")))
    return found


def interactive_gap_fill(pgn_text: str, errors: list[str]) -> str | None:
    """
    Present parse errors to the user and let them correct the PGN manually.
    Returns the corrected PGN string, or None if the user skips.
    """
    print("\n  PGN parse errors detected:")
    for err in errors:
        print(f"    - {err}")
    print("\n  Options:")
    print("  [e] Edit PGN manually (opens in $EDITOR)")
    print("  [s] Skip this PGN block")
    choice = input("  Choice [e/s]: ").strip().lower()

    if choice == "e":
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pgn", delete=False) as f:
            f.write(pgn_text)
            tmp_path = f.name
        editor = os.environ.get("EDITOR", "nano")
        os.system(f'{editor} "{tmp_path}"')
        corrected = Path(tmp_path).read_text()
        os.unlink(tmp_path)
        return corrected
    return None


def run(youtube_url: str, output_path: Path | None = None) -> Path:
    """
    Full Stage 1 run.  Returns path to the output .pgn file.
    Raises SystemExit on unrecoverable failure.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    info = fetch_video_info(youtube_url)
    title = info["title"]
    description = info["description"]

    # Sanitise title for use as a filename
    safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:80]
    if output_path is None:
        output_path = OUTPUT_DIR / f"{safe_title}.pgn"

    # Find all external URLs in the description
    urls = find_urls_in_text(description)
    print(f"[Stage 1] Found {len(urls)} URL(s) in description.")

    all_games = []
    for url in urls:
        # Skip YouTube links and known non-PGN domains
        parsed = urlparse(url)
        if "youtube" in parsed.netloc or "youtu.be" in parsed.netloc:
            continue

        pgn_blocks = scrape_pgn_from_url(url)
        for raw_pgn in pgn_blocks:
            games, errors = validate_pgn(raw_pgn)
            if games:
                print(f"    Found {len(games)} valid game(s) from {url}")
                all_games.extend(games)
            elif errors:
                corrected = interactive_gap_fill(raw_pgn, errors)
                if corrected:
                    games2, errors2 = validate_pgn(corrected)
                    if games2:
                        all_games.extend(games2)
                    else:
                        print(f"    Still invalid after edit — skipping. Errors: {errors2}")

    if not all_games:
        print(
            "\n[Stage 1] No valid PGN found in the video description.\n"
            "  Phase 2 (transcript extraction) is not yet implemented.\n"
            "  Try a video that links to a PGN in its description, or provide a PGN file directly.\n"
            "  Use:  python main.py review --pgn your_file.pgn"
        )
        sys.exit(1)

    pgn_out = games_to_pgn(all_games)
    output_path.write_text(pgn_out)
    print(f"\n[Stage 1] Done. {len(all_games)} game(s) written to {output_path}")
    return output_path
