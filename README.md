# YouTube → Chessable Course Automator

Converts a YouTube chess video into a ready-to-drill Chessable spaced-repetition course.

```
YouTube URL  →  PGN games  →  Lichess study (curate)  →  Chessable course
  Stage 1           Stage 2                                   Stage 3
```

Each stage can be run independently so you can re-run just the part you need.

---

## Prerequisites

### 1. Install dependencies

```bash
uv sync
uv run playwright install chromium
```

### 2. Create `.env` in the project root

```env
LICHESS_TOKEN=lip_xxxxxxxxxxxx
CHESSABLE_EMAIL=you@example.com
CHESSABLE_PASSWORD=yourpassword
```

**Getting a Lichess token:**
Go to https://lichess.org/account/oauth/token/create and create a token with the **Study read/write** scope.

### 3. (Optional) Edit `config.yaml`

```yaml
default_piece_color: Black   # White | Black | Both
```

---

## Full Pipeline (all three stages at once)

```bash
uv run python main.py run "https://www.youtube.com/watch?v=VIDEO_ID" --orientation black
```

This will:
1. Fetch PGN from the video description links (Stage 1)
2. Create a Lichess study, pause for you to curate it, then export the curated PGN (Stage 2)
3. Create a Chessable course and import the games as one chapter named after the video (Stage 3)

---

## Running Stages Individually

### Stage 1 — YouTube → PGN

Fetches the video description, finds external links that contain PGN, downloads and validates the games.

```bash
uv run python main.py fetch "https://www.youtube.com/watch?v=VIDEO_ID"
# Output: output/<video_title>.pgn
```

### Stage 2 — PGN → Lichess study → curated PGN

Creates a private Lichess study, imports your PGN into it for visual curation, then exports the curated result.

```bash
# Import a PGN into a new Lichess study
uv run python main.py review --pgn output/my_games.pgn --orientation black

# Re-export an existing study you've already curated
uv run python main.py review --export-study <STUDY_ID> --orientation black
# Output: output/<name>_curated.pgn
```

**What to do in Lichess between import and export:**
- Delete chapters/games you don't want
- Mark key moves with `!` (these become `{[%key]}` in the PGN and bold key moves on Chessable)
- Add arrows, circles, and text annotations

**Study settings required for export to work:**
- Visibility: **Unlisted** (not Private)
- Share & export: **Members** (not Nobody)

These are set automatically when the study is created by this tool. If you created the study manually, set them in the study gear menu.

### Stage 3 — Curated PGN → Chessable

Automates Chessable in a browser window (Playwright) to create chapters and import games.

#### Import into an existing chapter (default)

```bash
uv run python main.py import \
  --pgn output/my_games_curated.pgn \
  --auto \
  --course-id 419704 \
  --course-name "Black openings" \
  --chapter "Sicilian Defense: Accelerated Dragon"
```

The chapter must already exist in the course.

#### Create a new chapter and import

```bash
uv run python main.py import \
  --pgn output/my_games_curated.pgn \
  --auto \
  --course-id 419704 \
  --course-name "Black openings" \
  --new-chapter "Sicilian Defense: Accelerated Dragon"
```

**Where to find your course ID:**
Open the course control panel in Chessable. The URL will look like:
`https://www.chessable.com/bookadmin.php?bid=419704` — the number after `bid=` is the course ID.

---

## Adding a New Video to an Existing Course

This is the most common workflow once your course is set up:

```bash
# 1. Fetch PGN from the new video
uv run python main.py fetch "https://www.youtube.com/watch?v=NEW_VIDEO_ID"

# 2. Create a Lichess study, curate it, then export
uv run python main.py review --pgn output/<new_video_title>.pgn --orientation black
#    ↑ curate in Lichess (delete games, mark key moves), then press Enter to export

# 3. Import as a NEW chapter in the existing course
uv run python main.py import \
  --pgn output/<new_video_title>_curated.pgn \
  --auto \
  --course-id 419704 \
  --course-name "Black openings" \
  --new-chapter "<New Video Title>"
```

---

## CLI Reference

```
python main.py run <url> [--orientation white|black]
    Full pipeline: YouTube → Lichess → Chessable (creates new course + chapter)

python main.py fetch <url> [-o output/file.pgn]
    Stage 1 only: download PGN from a YouTube video description

python main.py review [--pgn file.pgn] [--export-study STUDY_ID]
                      [--lichess-study URL] [--orientation white|black]
                      [-o output/file_curated.pgn]
    Stage 2: PGN → Lichess study → curated PGN

python main.py import --pgn file.pgn [--auto]
                      [--course-id ID] [--course-name NAME]
                      [--chapter CHAPTER_NAME | --new-chapter CHAPTER_NAME]
    Stage 3: curated PGN → Chessable
      --auto             Use browser automation (default: copy to clipboard + open browser)
      --course-id        Chessable course ID (bid= from bookadmin URL)
      --course-name      Course display name (must match exactly — used in import dropdown)
      --chapter          Import into this existing chapter
      --new-chapter      Create this chapter, then import into it
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LICHESS_TOKEN` | Stage 2 | OAuth token with Study read/write scope |
| `CHESSABLE_EMAIL` | Stage 3 auto | Login email for Chessable |
| `CHESSABLE_PASSWORD` | Stage 3 auto | Login password for Chessable |

---

## Project Structure

```
youtube-chessable/
├── main.py                  # CLI entry point
├── stages/
│   ├── stage1_pgn.py        # YouTube → PGN
│   ├── stage2_lichess.py    # PGN → Lichess study → curated PGN
│   └── stage3_chessable.py  # Curated PGN → Chessable (Playwright)
├── utils/
│   └── pgn_utils.py         # PGN parsing, validation, annotation mapping
├── output/                  # Generated PGN files
├── docs/
│   └── chessable_page_map.md  # Chessable page structure notes (for future API)
├── test_stage3.py           # Quick test script for Stage 3
├── config.yaml              # Default settings
└── .env                     # Secrets (not committed)
```

---

## PGN Annotations & Key Moves

Chessable uses `{[%key]}` comments to mark which moves the learner must reproduce. This tool maps Lichess annotations automatically:

| In Lichess | In exported PGN | Effect on Chessable |
|---|---|---|
| `!` (good move) | `{ [%key] }` | Move is bolded — must be reproduced |
| No annotation | (nothing) | Move is trainable but not a key move |

**Tip:** Mark the most important moves with `!` in Lichess before exporting to control exactly what gets drilled on Chessable.
