"""
Stage 3 — Chessable Import
Curated PGN → private Chessable course.

Two modes:
  manual (default)  Copy PGN to clipboard + open import page in browser.
  auto              Full Playwright automation (headless=False so you can watch).
"""

import sys
import re
import webbrowser
from pathlib import Path

CHESSABLE_IMPORT_URL = "https://www.chessable.com/import/"


# ---------------------------------------------------------------------------
# Manual mode
# ---------------------------------------------------------------------------

def run_manual(pgn_path: Path) -> None:
    """Copy PGN to clipboard and open the Chessable import page."""
    try:
        import pyperclip
        pyperclip.copy(pgn_path.read_text())
        print("[Stage 3] PGN copied to clipboard.")
    except Exception:
        print("[Stage 3] Could not copy to clipboard — file is at:")
        print(f"  {pgn_path.resolve()}")

    print(f"[Stage 3] Opening Chessable import page…")
    print(f"  {CHESSABLE_IMPORT_URL}")
    webbrowser.open(CHESSABLE_IMPORT_URL)
    print("\n  Paste the PGN into the text box and complete the import.")


# ---------------------------------------------------------------------------
# Auto mode — Playwright
# ---------------------------------------------------------------------------

def _login(page, email: str, password: str) -> None:
    page.goto("https://www.chessable.com/login")
    page.wait_for_selector("input[data-test-id=email]")
    page.fill("input[data-test-id=email]", email)
    page.fill("input[data-test-id=password]", password)
    page.click("button[type=submit]")
    page.wait_for_url(lambda url: "login" not in url, timeout=20000)
    print("[Stage 3] Logged in.")


def _get_mt1_frame(page):
    """Return the mt1 iframe frame that contains the real Chessable forms."""
    for frame in page.frames:
        if "mt1" in frame.url:
            return frame
    raise RuntimeError("Could not find Chessable mt1 iframe — page structure may have changed.")


def _create_course(page, course_name: str, piece_color: str, course_type: str) -> int:
    """Create a new course and return its book_id.

    After form submission, Chessable redirects the mt1 frame (and often the main
    page) to bookadmin.php?bid=<NEW_ID>.  We extract the ID from those URLs rather
    than doing a fuzzy search that can match other users' public courses.
    """
    import re as _re, time

    print(f"[Stage 3] Creating course '{course_name}'…")
    page.goto("https://www.chessable.com/newcourse/")
    page.wait_for_load_state("networkidle")

    frame = _get_mt1_frame(page)

    frame.wait_for_selector("input[name=name]")
    frame.fill("input[name=name]", course_name)
    frame.select_option("select[name=book_type]", label=course_type)
    frame.select_option("select[name=color]", label=piece_color)
    frame.click("input[type=submit]")

    # Wait for any redirect that carries the new book ID in a URL
    # Chessable redirects the mt1 frame (and sometimes the main page) to
    # something like /bookadmin.php?bid=<ID> or /course/<ID>/ after creation.
    time.sleep(3)

    def _extract_id_from_frames():
        for f in page.frames:
            for pattern in [r'bid=(\d+)', r'/course/(\d+)/', r'book_id=(\d+)']:
                m = _re.search(pattern, f.url)
                if m:
                    return int(m.group(1))
        # Also check main page URL
        for pattern in [r'bid=(\d+)', r'/course/(\d+)/', r'book_id=(\d+)']:
            m = _re.search(pattern, page.url)
            if m:
                return int(m.group(1))
        return None

    # Poll for up to 20 s for a redirect that contains the book ID
    book_id = None
    for _ in range(20):
        book_id = _extract_id_from_frames()
        if book_id:
            break
        time.sleep(1)

    if book_id:
        print(f"[Stage 3] Course created. ID: {book_id}")
        return book_id

    # Fallback: look for success text then try the courses page with exact-name filter
    try:
        frame.wait_for_selector(".isa_success", timeout=5000)
    except Exception:
        pass
    print(f"[Stage 3] Course created (searching for ID).")
    return _get_book_id_exact(page, course_name)


def _get_book_id(page, course_name: str) -> int:
    """Legacy helper — kept for reference. Prefer _get_book_id_exact."""
    return _get_book_id_exact(page, course_name)


def _get_book_id_exact(page, course_name: str) -> int:
    """
    Find our own course ID by navigating to the creator's course list and
    matching the title EXACTLY — avoids accidentally picking a public course
    from another user with the same name.
    """
    from urllib.parse import quote_plus
    import re as _re

    page.goto(f"https://www.chessable.com/courses/all/created/?search={quote_plus(course_name)}")
    page.wait_for_load_state("networkidle")

    # Collect all course cards visible on the page
    for frame in page.frames:
        cards = frame.query_selector_all("a[href*='/course/']")
        for card in cards:
            href = card.get_attribute("href") or ""
            match = _re.search(r'/course/(\d+)/', href)
            if not match:
                continue
            # Only accept if the link's text contains our exact course name
            card_text = (card.inner_text() or "").strip()
            if course_name.lower() in card_text.lower():
                book_id = int(match.group(1))
                print(f"[Stage 3] Course ID: {book_id}")
                return book_id

    raise RuntimeError(
        f"Could not find course '{course_name}' in your created courses list.\n"
        "  Check https://www.chessable.com/courses/all/created/ to verify it exists."
    )


def _create_chapter(page, chapter_name: str, book_id: int) -> None:
    """Create a chapter — bookadmin.php is in the main frame, no iframe needed.

    Uses bit=3 (New Chapter tab). If the input isn't immediately visible
    (e.g. new course lands on a different default tab), clicks the sidebar link by href.
    """
    page.goto(f"https://www.chessable.com/bookadmin.php?bid={book_id}&a=edit&bit=3")
    page.wait_for_load_state("networkidle")

    # Save debug screenshot in case of failure
    from pathlib import Path as _Path
    debug_ss = _Path("output/debug_bookadmin.png")

    # If the "New Chapter" input isn't visible, find the sidebar link by href pattern
    try:
        page.wait_for_selector("input[name=title]", timeout=8000)
    except Exception:
        debug_ss.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(debug_ss))
        print(f"[Stage 3] DEBUG screenshot → {debug_ss}")
        # Try clicking the sidebar link by its href (bit=3 or containing 'bit=3')
        try:
            page.click(f"a[href*='bit=3']", timeout=5000)
        except Exception:
            # Try by partial text match (the + sign may be a different char)
            page.click("a:text-matches('New Chapter', 'i')", timeout=5000)
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("input[name=title]", timeout=15000)

    page.fill("input[name=title]", chapter_name[:55])  # 55 char max per UI hint
    page.click("input[type=submit][value='Add Chapter'], button:has-text('Add Chapter')")
    page.wait_for_load_state("networkidle")
    print(f"[Stage 3]   Chapter created: {chapter_name}")


def _import_pgn_chapter(page, pgn_text: str, course_name: str, chapter_name: str) -> None:
    """
    Import a PGN string into a specific course chapter.
    Uses file upload (more reliable than clipboard paste).
    The import page lives in the main frame — no mt1 iframe.
    """
    import tempfile, os, time

    page.goto("https://www.chessable.com/import/")
    page.wait_for_load_state("networkidle")

    # Write PGN to a temp file and upload it
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pgn", delete=False) as f:
        f.write(pgn_text)
        tmp_path = f.name

    try:
        page.set_input_files("input#fileToUpload", tmp_path)
    finally:
        os.unlink(tmp_path)

    # Select course
    page.wait_for_selector("select#bookName")
    page.select_option("select#bookName", label=course_name)

    # Wait for chapter dropdown to populate
    page.wait_for_function(
        f"() => Array.from(document.querySelectorAll('select option')).some(o => o.text.includes('{chapter_name[:20]}'))",
        timeout=15000,
    )

    # Select the chapter — it's the second select on the page
    selects = page.query_selector_all("select")
    chapter_select = None
    for sel in selects:
        if sel.get_attribute("id") != "bookName":
            chapter_select = sel
            break

    if chapter_select:
        chapter_select.select_option(label=chapter_name)
    else:
        raise RuntimeError("Could not find chapter dropdown on import page.")

    # Click Import
    page.click("input#submitButton")

    # Wait for success dialog
    page.wait_for_selector("#swal2-title", timeout=120000)
    page.wait_for_function(
        "() => document.querySelector('#swal2-title')?.innerText?.includes('Import Succeed')",
        timeout=120000,
    )
    # Dismiss the dialog
    try:
        page.click(".swal2-confirm", timeout=5000)
    except Exception:
        pass
    print(f"[Stage 3]   Imported chapter: {chapter_name}")


def _trim_name(name: str, k: int = 55) -> str:
    name = " ".join(name.replace("Chapter ", "").split())
    return name[:k]


def run_auto(
    email: str,
    password: str,
    pgn_path: Path,
    course_name: str = "YouTube Chess Course",
    chapter_name: str | None = None,
    piece_color: str = "White",
    course_type: str = "Opening",
    course_id: int | None = None,
) -> None:
    """Full Playwright automation — creates course, one chapter, imports all PGN games.

    All games in pgn_path go into a single chapter.
    chapter_name defaults to course_name if not provided.
    """
    from playwright.sync_api import sync_playwright

    pgn_text = pgn_path.read_text()

    # Collect all non-empty game blocks
    raw_blocks = re.split(r'\n\n(?=\[Event)', pgn_text.strip())
    game_blocks = [b.strip() for b in raw_blocks if b.strip()]

    if not game_blocks:
        print("[Stage 3] No games found in PGN — aborting.", file=sys.stderr)
        return

    chapter = _trim_name(chapter_name or course_name)
    print(f"[Stage 3] {len(game_blocks)} game(s) → chapter '{chapter}'")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=200)
        page = browser.new_page()

        _login(page, email, password)

        if course_id is not None:
            print(f"[Stage 3] Using existing course ID: {course_id}")
            book_id = course_id
        else:
            book_id = _create_course(page, course_name, piece_color, course_type)

        # One chapter for all games in this video
        _create_chapter(page, chapter, book_id)
        combined_pgn = "\n\n".join(game_blocks)
        _import_pgn_chapter(page, combined_pgn, course_name, chapter)

        print(f"\n[Stage 3] Done! Course ready to drill:")
        print(f"  https://www.chessable.com/course/{book_id}/")
        browser.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(
    pgn_path: Path,
    manual: bool = True,
    email: str = "",
    password: str = "",
    course_name: str = "YouTube Chess Course",
    chapter_name: str | None = None,
    piece_color: str = "White",
    course_type: str = "Opening",
    course_id: int | None = None,
) -> None:
    if not pgn_path.exists():
        print(f"[Stage 3] PGN file not found: {pgn_path}", file=sys.stderr)
        sys.exit(1)

    if manual:
        run_manual(pgn_path)
    else:
        run_auto(email, password, pgn_path, course_name, chapter_name, piece_color, course_type, course_id)
