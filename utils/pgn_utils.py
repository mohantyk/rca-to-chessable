"""PGN extraction and validation helpers."""

import re
import io
import chess
import chess.pgn


# Patterns that indicate a PGN block in raw text
_PGN_HEADER_RE = re.compile(r'^\[Event\s+"', re.MULTILINE)
_MOVE_RE = re.compile(r'\b1\.\s*[A-Za-z]')


def extract_pgn_blocks(text: str) -> list[str]:
    """
    Find all PGN blocks in a blob of text (e.g. scraped webpage HTML converted
    to plain text, or a raw description).  Returns a list of raw PGN strings.
    """
    blocks = []
    # Split on [Event " markers — each one starts a new game
    parts = re.split(r'(?=\[Event\s+")', text)
    for part in parts:
        part = part.strip()
        if part.startswith('[Event "') and _MOVE_RE.search(part):
            blocks.append(part)
    return blocks


def extract_pgn_from_scripts(html: str) -> list[str]:
    """
    Extract PGN strings embedded in JavaScript, e.g. RPBChessboard.renderPGN()
    calls used by chess-teacher.com and similar WordPress chess plugins.

    Handles JSON-encoded PGN where \\n and \\" are escaped.
    """
    import json
    blocks = []

    # Match: RPBChessboard.renderPGN("id", {"pgn":"..."})
    pattern = re.compile(
        r'RPBChessboard\.renderPGN\(\s*"[^"]+"\s*,\s*(\{[^;]+?\})\s*\)',
        re.DOTALL,
    )
    for m in pattern.finditer(html):
        try:
            obj = json.loads(m.group(1))
            pgn = obj.get("pgn", "")
            if pgn and _MOVE_RE.search(pgn):
                blocks.append(pgn)
        except json.JSONDecodeError:
            # Fall back to simple regex extraction of the pgn value
            pgn_match = re.search(r'"pgn"\s*:\s*"((?:[^"\\]|\\.)*)"', m.group(1))
            if pgn_match:
                pgn = pgn_match.group(1).encode().decode('unicode_escape')
                if _MOVE_RE.search(pgn):
                    blocks.append(pgn)

    return blocks


def validate_pgn(pgn_text: str) -> tuple[list[chess.pgn.Game], list[str]]:
    """
    Parse a PGN string with python-chess.  Returns (valid_games, errors).
    valid_games is a list of chess.pgn.Game objects.
    errors is a list of human-readable error strings.
    """
    games = []
    errors = []
    stream = io.StringIO(pgn_text)
    while True:
        try:
            game = chess.pgn.read_game(stream)
        except Exception as exc:
            errors.append(f"Parse error: {exc}")
            break
        if game is None:
            break
        # Check for errors stored by python-chess in the game object
        if game.errors:
            for err in game.errors:
                errors.append(str(err))
        else:
            games.append(game)
    return games, errors


def games_to_pgn(games: list[chess.pgn.Game]) -> str:
    """Serialise a list of chess.pgn.Game objects back to a PGN string."""
    out = []
    for game in games:
        # Fresh exporter per game — reusing one exporter accumulates all prior output
        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        out.append(game.accept(exporter))
    return "\n\n".join(out)


def map_annotations_to_key_moves(pgn_text: str) -> str:
    """
    Replace Lichess '!' annotation (NAG $1) with a Chessable {[%key]} comment.
    Lichess exports '!' as the NAG '$1' appended after a move.
    Chessable reads {[%key]} comments to identify key moves.

    Input:  ...14. Nf3 $1 { some comment }...
    Output: ...14. Nf3 { [%key] some comment }...
    """
    # $1 with an existing comment: merge [%key] into the comment
    pgn_text = re.sub(
        r'\$1\s*\{([^}]*)\}',
        lambda m: '{ [%key] ' + m.group(1).strip() + ' }',
        pgn_text,
    )
    # $1 with no comment: add a fresh {[%key]} comment
    pgn_text = re.sub(r'\$1(?!\s*\{)', ' { [%key] }', pgn_text)
    return pgn_text
