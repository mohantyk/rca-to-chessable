# Chessable Page Map & Navigation Notes

Compiled from live Playwright automation runs + official course creation guide.
Use this as the foundation for a future Chessable REST/browser API.

Sources:
- Live Playwright sessions against chessable.com (on a private test course)
- Official guide: https://go.chessable.com/create/chessable-course-creation-guide/

---

## Course Structure Concepts (from official docs)

### Course Types
| Type | Training mode | Use for |
|------|--------------|---------|
| `Opening` | Learn mode (hints) | Opening repertoires |
| `Tactics` | Puzzle mode (no hints) | Puzzles — first & last moves must be key moves |
| `Strategy` | Learn mode (hints) | Positional/strategic ideas |
| `Endgame` | Learn mode (hints) | Endgame technique |

- **Tactics courses** ask users to solve immediately without hints.
- **Non-tactics courses** show hints; only first move (and auto-last) must be a key move.
- "Enable tactics functionality" toggle in Control Panel can mix both modes in one course.

### Color / Orientation
- `White` / `Black` → automatically sets all trainable lines to that side's perspective.
- `Both` → requires manual per-line color assignment after import.
- Can be changed after creation via Course Information tab in Control Panel.

### Chapter / Line Hierarchy
```
Course
 └─ Chapter (named, e.g. "Accelerated Dragon Lines")
     └─ Variation (trainable line, one per game or sub-variation)
         └─ Key moves  ← bolded; what the user must remember
```
- Courses start with one default chapter: **"Main Level"** — rename or delete it.
- Each chapter contains multiple trainable variations (games/lines).
- **One chapter per video** is our convention (all games from that video together).

### PGN Format Requirements
These must be correct or the import will fail silently or give wrong results:

| Requirement | Correct | Wrong |
|---|---|---|
| Move spacing | `1. e4 e5` | `1.e4 e5` |
| Castling | `O-O` (letter O) | `0-0` (zero) |
| Annotations | `{ comment text }` | — |
| NAG symbols | `$1` for `!`, `$2` for `?` | — |
| Key move marker | `{ [%key] }` | — |
| Subvariations | `( 1. d4 )` in parentheses | — |
| Non-clickable text in sub-var | `[text in brackets]` | — |

### Import Options (on the `/import/` page)
- **"Import all sub-variations as their own item"** toggle:
  - ✅ Enabled → each sub-variation becomes its own trainable line (use for openings)
  - ❌ Disabled → only main line is trainable; sub-variations are annotations (use for games)
- **Duplicate variation allowance** toggle — allow or block duplicate lines.
- **Variation title formatting** — controls how line titles are auto-named.

### Key Moves
- Bolded moves = key moves = what the user must reproduce during training.
- Our `{ [%key] }` comment in PGN sets the move before it as a key move.
- **Automatic key move selection** is available in the Control Panel — useful if `{ [%key] }` wasn't set in the PGN.
- Soft fail: engine evaluates within ±0.3 centipawn tolerance for "close enough" answers.

### Publishing Standards (for public courses)
- Every 3 moves must have an annotation or visual cue.
- Variation conclusions must be annotated.
- Opening courses must include an **Annotated Games** chapter and (if 200+ lines) a **Quickstarter** chapter.
- Professional English, original content only.

---

## Authentication

### Login Page
- **URL:** `https://www.chessable.com/login`
- **Frame:** main
- **Selectors:**
  - Email field: `input[data-test-id="email"]`
  - Password field: `input[data-test-id="password"]`
  - Submit button: `button[type="submit"]`
- **Success signal:** URL no longer contains `"login"` (redirect to dashboard)
- **Timeout:** Allow 20 s for redirect (slow network / 2FA possible)

---

## Course Creation

### New Course Page
- **URL:** `https://www.chessable.com/newcourse/`
- **Frame:** ⚠️ **mt1 iframe** — NOT the main frame
  - The mt1 iframe URL matches the pattern `*/mt1/*`
  - Enumerate `page.frames` and pick the one whose `.url` contains `"mt1"`
- **Key selectors (inside mt1 frame):**
  - Course name: `input[name="name"]`
  - Course type: `select[name="book_type"]` — options: `"Opening"`, `"Tactics"`, `"Strategy"`, `"Endgame"`
  - Piece color: `select[name="color"]` — options: `"White"`, `"Black"`, `"Both"`
  - Submit: `input[type="submit"]`
- **Success signals (check in order):**
  1. `.isa_success` appears in the mt1 frame (fast path)
  2. `document.body.innerText.includes('was added')` in the main page (fallback)
  3. Page reaches `networkidle` state (last resort)
- **Notes:**
  - The form is a classic PHP form-post inside the iframe — no React/SPA here.
  - Course name has a practical max of 55 characters (truncate before filling).

---

## Course Listing / ID Lookup

### Created Courses Page
- **URL:** `https://www.chessable.com/courses/all/created/?search=<encoded_name>`
- **Frame:** main (no mt1 iframe on this page)
- **How to extract the course ID:**
  - Query all frames for `a[href*="/course/"]` links
  - Extract the numeric ID with: `re.search(r'/course/(\d+)/', href)`
  - The first match is the most-recently-created matching course
- **Notes:**
  - URL-encode the course name with `urllib.parse.quote_plus`
  - The search is fuzzy — verify the name matches before returning the ID

---

## Chapter Management

### Book Admin Page (Add Chapter)
- **URL:** `https://www.chessable.com/bookadmin.php?bid=<BOOK_ID>&a=edit&bit=3`
- **Frame:** main
- **Selectors:**
  - Chapter title: `input[name="title"]`
  - Submit: `input[type="submit"][value="Add Chapter"]` or `button:has-text("Add Chapter")`
- **Notes:**
  - `bit=3` is the "Chapters" tab — other `bit` values go to different admin tabs
  - Chapter name max length: 55 characters (enforced by UI hint — truncate in code)
  - After submit, wait for `networkidle` before navigating away

---

## PGN Import

### Import Page
- **URL:** `https://www.chessable.com/import/`
- **Frame:** main
- **Upload method:** File upload (more reliable than clipboard paste in automated contexts)
- **Selectors & workflow:**
  1. Upload PGN file: `input#fileToUpload`
     → Write PGN to a temp `.pgn` file, use `page.set_input_files(selector, path)`
  2. Course selector: `select#bookName`
     → Select by `label=` (course display name)
  3. Chapter selector: second `<select>` on the page that is NOT `#bookName`
     → Wait for it to populate: `page.wait_for_function("() => Array.from(document.querySelectorAll('select option')).some(o => o.text.includes('<chapter_prefix>'))")`
     → Select by `label=` (chapter display name)
  4. Import button: `input#submitButton`
- **Success detection:**
  - SweetAlert2 modal appears: `#swal2-title` with inner text `"Import Succeed"`
  - Timeout budget: 120 s (Chessable server can be slow)
  - Dismiss: click `.swal2-confirm`
- **Additional import options on the page** (checkboxes/toggles — automate by ID once confirmed):
  - "Import all sub-variations as their own item" — enable for opening courses
  - "Allow duplicate variations" — disable to avoid re-importing the same lines
  - "Variation title formatting" — affects how line names are auto-generated
- **Notes:**
  - Delete the temp file immediately after `set_input_files()` — use `try/finally`
  - The chapter dropdown only populates after the course is selected; always wait before querying it
  - Error case: import page shows an error banner if PGN is malformed or duplicate — check for `#swal2-title` text other than `"Import Succeed"` and surface it
  - PGN format pitfalls: must use `O-O` (letter) not `0-0` (zero) for castling; spaces after move numbers required (`1. e4` not `1.e4`)

---

## Course Study/Drill Page

### Course Home
- **URL:** `https://www.chessable.com/course/<BOOK_ID>/`
- Useful for verification after import — user can open this directly
- No automation notes yet (future: scrape variation counts, chapter names)

---

## Full Page Frame Map

| URL Pattern | Frame | Notes |
|---|---|---|
| `/login` | main | Standard React login form |
| `/newcourse/` | **mt1 iframe** | Classic PHP form inside iframe |
| `/courses/all/created/` | main | SPA listing — search by query param |
| `/bookadmin.php` | main | PHP admin — `bit` param controls tab |
| `/import/` | main | SPA import form with SweetAlert2 dialogs |
| `/course/<id>/` | main | Course drill/study SPA |

---

## Why the `kamui-fin/chessable-import` Repo Didn't Work

The GitHub repo `kamui-fin/chessable-import` was written for a much older version of Chessable (ca. 2020–2021). Key differences:

1. **Old selectors are gone:** `.whiteBodyContainer form`, `.chessable-form-control`, etc. no longer exist. Chessable has since rewritten their frontend in React.
2. **Import flow changed:** The old library used clipboard paste via `pyperclip` + keyboard events. The current import page uses a proper `<input type="file">` element.
3. **Course creation moved to iframe:** The `/newcourse/` form is now inside an mt1 iframe, which the old Selenium-based library didn't account for.
4. **Login selectors changed:** Old library targeted generic `input[type=email]`; current page uses `data-test-id` attributes.
5. **No maintained release:** Last commit was 2021; no PyPI package; the repo has no test suite.

→ Decision: Playwright from scratch, with selectors verified against the live site.

---

## Notes for Future API

### Authentication Strategy
- **Session cookies:** After `_login()` succeeds, Playwright's browser context holds the session cookie automatically. For a standalone API, extract cookies via `page.context.cookies()` and reuse them in `requests.Session`.
- **Token API:** Chessable does not expose a public REST API with token auth (as of 2024). All automation must go through the browser UI or reverse-engineer the internal XHR calls.

### Potential XHR Endpoints (to explore with DevTools)
Intercept network requests during a manual session (`page.on("request", ...)`) to find:
- The XHR that creates a course (look for POST to `/api/...` or `/bookadmin.php`)
- The XHR that adds a chapter
- The XHR that the import page fires after file upload

If these exist as clean JSON APIs, they can replace the full Playwright automation with lightweight `requests` calls, which would be faster and more reliable.

### Recommended DevTools Approach
1. Open Chessable in Chrome DevTools → Network tab → filter `Fetch/XHR`
2. Perform each action manually (create course, add chapter, import PGN)
3. Note the request URL, method, headers (especially `X-CSRFToken`, `Authorization`)
4. Check if the same endpoint is callable with just the session cookie
5. If yes → replace Playwright automation with `requests.Session` calls

---

*Last updated: 2026-03-31. Based on live tests + official guide: https://go.chessable.com/create/chessable-course-creation-guide/*
