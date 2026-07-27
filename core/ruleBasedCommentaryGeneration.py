"""
Rule-based commentary generation for a chess position.

Everything here is deterministic pattern detection over the board - no
engine evaluation involved. This is meant to sit alongside engine-driven
analysis (StockfishEngine / MoveEval / TreeNode.eval_delta_cp) as a second,
complementary source of per-node commentary for CALT's game tree: the
engine says *how good* a move is, this module says *why* the position looks
the way it does (what's attacked, who controls the center, pawn weaknesses,
king exposure).

Covers:
  - checks, captures, and attacks available in the position
  - center control (occupation + attacker counts on d4/e4/d5/e5)
  - every attacked piece, with its attackers and defenders
  - pawn structure (doubled/tripled/quadrupled, isolated/passed pawns, open/half-open files)
  - king safety (castling status, pawn shield, open files near the king)
  - material balance

Usage:
    from core.ruleBasedCommentaryGeneration import generate_commentary, analyze_position

    print(generate_commentary(board))       # human-readable text
    report = analyze_position(board)         # structured PositionReport
"""

from dataclasses import dataclass, field

import chess

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

CENTER_SQUARES = [chess.D4, chess.E4, chess.D5, chess.E5]


def _color_name(color: bool) -> str:
    return "White" if color == chess.WHITE else "Black"


def _piece_name(piece: chess.Piece) -> str:
    return f"{_color_name(piece.color).lower()} {chess.piece_name(piece.piece_type)}"


# ---- structured report types -------------------------------------------------

@dataclass
class AttackedPieceReport:
    square: str
    piece: str                  # e.g. "black knight"
    attackers: list[str]        # e.g. ["white bishop on c4"]
    defenders: list[str]
    is_hanging: bool            # attacked with no defenders at all


@dataclass
class CenterControlReport:
    occupants: dict[str, str | None]              # square name -> piece description, or None
    attacker_counts: dict[str, tuple[int, int]]    # square name -> (white_attackers, black_attackers)
    white_score: int                                # occupation + attacker count, simple weighting
    black_score: int


@dataclass
class PawnStructureReport:
    doubled: dict[str, list[str]]          # "white"/"black" -> file letters with exactly 2 pawns
    tripled: dict[str, list[str]]          # "white"/"black" -> file letters with exactly 3 pawns
    quadrupled: dict[str, list[str]]       # "white"/"black" -> file letters with 4+ pawns (rare, but possible via promotion)
    isolated: dict[str, list[str]]         # "white"/"black" -> square names of isolated pawns
    passed: dict[str, list[str]]           # "white"/"black" -> square names of passed pawns
    open_files: list[str]                  # file letters with no pawns at all
    half_open_files: dict[str, list[str]]  # "white"/"black" -> files open *for* that color


@dataclass
class KingSafetyReport:
    color: str
    in_check: bool
    can_castle_kingside: bool
    can_castle_queenside: bool
    appears_castled: bool
    pawn_shield_intact: bool | None      # None if not applicable (king hasn't castled)
    open_files_adjacent: list[str]        # open/half-open files touching the king's file


@dataclass
class MaterialReport:
    white_total: int
    black_total: int
    difference: int   # positive => White is ahead


@dataclass
class PositionReport:
    side_to_move: str          # "White" or "Black" - whose move it is in this position
    move_played: str | None    # description of the move that led to this position, or None at a tree root
    checks: list[str]
    captures: list[str]
    attacked_pieces: list[AttackedPieceReport]
    center_control: CenterControlReport
    pawn_structure: PawnStructureReport
    king_safety: list[KingSafetyReport]   # [white, black]
    material: MaterialReport


# ---- checks / captures --------------------------------------------------------

def _analyze_checks_and_captures(board: chess.Board) -> tuple[list[str], list[str]]:
    checks = []
    if board.is_check():
        checks.append(f"{_color_name(board.turn)} is in check.")

    captures = []
    for move in board.legal_moves:
        if not board.is_capture(move):
            continue
        attacker = board.piece_at(move.from_square)
        if board.is_en_passant(move):
            captured_desc = "pawn (en passant)"
        else:
            captured = board.piece_at(move.to_square)
            captured_desc = chess.piece_name(captured.piece_type) if captured else "piece"
        captures.append(
            f"{chess.piece_name(attacker.piece_type)} on {chess.square_name(move.from_square)} "
            f"can capture the {captured_desc} on {chess.square_name(move.to_square)}"
        )
    return checks, captures


# ---- center control -----------------------------------------------------------

def _analyze_center_control(board: chess.Board) -> CenterControlReport:
    occupants = {}
    attacker_counts = {}
    white_score = 0
    black_score = 0

    for square in CENTER_SQUARES:
        name = chess.square_name(square)
        piece = board.piece_at(square)
        occupants[name] = _piece_name(piece) if piece else None
        if piece:
            (white_score, black_score) = (
                (white_score + 1, black_score) if piece.color == chess.WHITE else (white_score, black_score + 1)
            )

        white_attackers = len(board.attackers(chess.WHITE, square))
        black_attackers = len(board.attackers(chess.BLACK, square))
        attacker_counts[name] = (white_attackers, black_attackers)
        white_score += white_attackers
        black_score += black_attackers

    return CenterControlReport(occupants, attacker_counts, white_score, black_score)


# ---- attacked pieces -----------------------------------------------------------

def _analyze_attacked_pieces(board: chess.Board) -> list[AttackedPieceReport]:
    reports = []
    for square, piece in board.piece_map().items():
        enemy_color = not piece.color
        attackers = board.attackers(enemy_color, square)
        if not attackers:
            continue
        defenders = board.attackers(piece.color, square)

        attacker_descs = [
            f"{_piece_name(board.piece_at(sq))} on {chess.square_name(sq)}" for sq in attackers
        ]
        defender_descs = [
            f"{_piece_name(board.piece_at(sq))} on {chess.square_name(sq)}" for sq in defenders
        ]

        reports.append(
            AttackedPieceReport(
                square=chess.square_name(square),
                piece=_piece_name(piece),
                attackers=attacker_descs,
                defenders=defender_descs,
                is_hanging=(len(defenders) == 0),
            )
        )
    return reports


# ---- pawn structure -------------------------------------------------------------

def _pawns_by_file(board: chess.Board, color: bool) -> dict[int, list[int]]:
    files: dict[int, list[int]] = {f: [] for f in range(8)}
    for square in board.pieces(chess.PAWN, color):
        files[chess.square_file(square)].append(chess.square_rank(square))
    return files


def _is_passed_pawn(board: chess.Board, square: int, color: bool) -> bool:
    file = chess.square_file(square)
    rank = chess.square_rank(square)
    enemy = not color
    for f in (file - 1, file, file + 1):
        if f < 0 or f > 7:
            continue
        for sq in board.pieces(chess.PAWN, enemy):
            if chess.square_file(sq) != f:
                continue
            erank = chess.square_rank(sq)
            if (color == chess.WHITE and erank > rank) or (color == chess.BLACK and erank < rank):
                return False
    return True


def _analyze_pawn_structure(board: chess.Board) -> PawnStructureReport:
    doubled = {"white": [], "black": []}
    tripled = {"white": [], "black": []}
    quadrupled = {"white": [], "black": []}
    isolated = {"white": [], "black": []}
    passed = {"white": [], "black": []}

    white_files = _pawns_by_file(board, chess.WHITE)
    black_files = _pawns_by_file(board, chess.BLACK)

    for color, files, key in ((chess.WHITE, white_files, "white"), (chess.BLACK, black_files, "black")):
        for f, ranks in files.items():
            count = len(ranks)
            if count == 2:
                doubled[key].append(chess.FILE_NAMES[f])
            elif count == 3:
                tripled[key].append(chess.FILE_NAMES[f])
            elif count >= 4:
                quadrupled[key].append(chess.FILE_NAMES[f])
            left_has = bool(files.get(f - 1)) if f - 1 >= 0 else False
            right_has = bool(files.get(f + 1)) if f + 1 <= 7 else False
            if ranks and not left_has and not right_has:
                for rank in ranks:
                    sq = chess.square(f, rank)
                    isolated[key].append(chess.square_name(sq))
        for square in board.pieces(chess.PAWN, color):
            if _is_passed_pawn(board, square, color):
                passed[key].append(chess.square_name(square))

    open_files = []
    half_open = {"white": [], "black": []}
    for f in range(8):
        w = bool(white_files.get(f))
        b = bool(black_files.get(f))
        if not w and not b:
            open_files.append(chess.FILE_NAMES[f])
        elif not w and b:
            half_open["white"].append(chess.FILE_NAMES[f])   # open *for* White (no white pawn blocking)
        elif w and not b:
            half_open["black"].append(chess.FILE_NAMES[f])

    return PawnStructureReport(doubled, tripled, quadrupled, isolated, passed, open_files, half_open)


# ---- king safety ------------------------------------------------------------------

_CASTLED_KINGSIDE_SQUARES = {chess.WHITE: chess.G1, chess.BLACK: chess.G8}
_CASTLED_QUEENSIDE_SQUARES = {chess.WHITE: chess.C1, chess.BLACK: chess.C8}
_SHIELD_SQUARES = {
    (chess.WHITE, "kingside"): [chess.F2, chess.G2, chess.H2],
    (chess.WHITE, "queenside"): [chess.B2, chess.C2, chess.D2],
    (chess.BLACK, "kingside"): [chess.F7, chess.G7, chess.H7],
    (chess.BLACK, "queenside"): [chess.B7, chess.C7, chess.D7],
}


def _analyze_king_safety(board: chess.Board, color: bool, pawn_structure: PawnStructureReport) -> KingSafetyReport:
    king_square = board.king(color)
    side = None
    if king_square == _CASTLED_KINGSIDE_SQUARES[color]:
        side = "kingside"
    elif king_square == _CASTLED_QUEENSIDE_SQUARES[color]:
        side = "queenside"
    appears_castled = side is not None

    pawn_shield_intact = None
    if appears_castled:
        shield_squares = _SHIELD_SQUARES[(color, side)]
        pawn_shield_intact = all(
            board.piece_at(sq) is not None
            and board.piece_at(sq).piece_type == chess.PAWN
            and board.piece_at(sq).color == color
            for sq in shield_squares
        )

    king_file = chess.FILE_NAMES[chess.square_file(king_square)]
    open_and_half_open = set(pawn_structure.open_files) | set(
        pawn_structure.half_open_files["white"] + pawn_structure.half_open_files["black"]
    )
    adjacent_files = {
        chess.FILE_NAMES[f]
        for f in (chess.square_file(king_square) - 1, chess.square_file(king_square), chess.square_file(king_square) + 1)
        if 0 <= f <= 7
    }
    open_files_adjacent = sorted(open_and_half_open & adjacent_files)

    return KingSafetyReport(
        color=_color_name(color),
        in_check=board.is_check() and board.turn == color,
        can_castle_kingside=board.has_kingside_castling_rights(color),
        can_castle_queenside=board.has_queenside_castling_rights(color),
        appears_castled=appears_castled,
        pawn_shield_intact=pawn_shield_intact,
        open_files_adjacent=open_files_adjacent,
    )


# ---- material ------------------------------------------------------------------------

def _analyze_material(board: chess.Board) -> MaterialReport:
    white_total = sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if p.color == chess.WHITE)
    black_total = sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if p.color == chess.BLACK)
    return MaterialReport(white_total, black_total, white_total - black_total)


def describe_move(board_before: chess.Board, move: chess.Move, board_after: chess.Board) -> str:
    """
    Plain-language description of what a move actually did, e.g.
    "Black rook on b3 captures the white pawn on b2." Requires the board
    *before* the move (so the captured piece/mover are still readable) and
    the board *after* (to report check/checkmate).
    """
    mover = board_before.piece_at(move.from_square)
    color_name = _color_name(mover.color)
    piece_name = chess.piece_name(mover.piece_type)
    from_sq = chess.square_name(move.from_square)
    to_sq = chess.square_name(move.to_square)

    if board_before.is_castling(move):
        side = "kingside" if chess.square_file(move.to_square) == 6 else "queenside"
        desc = f"{color_name} castles {side}."
    elif board_before.is_en_passant(move):
        desc = f"{color_name} {piece_name} on {from_sq} captures en passant on {to_sq}."
    elif board_before.is_capture(move):
        captured = board_before.piece_at(move.to_square)
        captured_name = _piece_name(captured) if captured else "piece"
        desc = f"{color_name} {piece_name} on {from_sq} captures the {captured_name} on {to_sq}."
    else:
        desc = f"{color_name} {piece_name} moves from {from_sq} to {to_sq}."

    if move.promotion:
        desc += f" Promotes to {chess.piece_name(move.promotion)}."

    if board_after.is_checkmate():
        desc += " Checkmate."
    elif board_after.is_check():
        desc += " Check."

    return desc


# ---- top-level API ------------------------------------------------------------------------

def _game_over_message(board: chess.Board) -> str | None:
    """
    Returns a short terminal-state message if the game has ended, or None
    if it's still in progress. For checkmate this is "{color} won"; other
    terminations (stalemate, insufficient material, etc.) report "Draw".
    """
    if not board.is_game_over():
        return None
    outcome = board.outcome()
    if outcome is None:
        return None
    if outcome.winner is not None:
        return f"{_color_name(outcome.winner)} won"
    return "Draw"


def _describe_last_move(board: chess.Board) -> str | None:
    """
    If `board` was reached by playing a move (i.e. it has history in
    board.move_stack - true for any board built via .copy()/.push() rather
    than parsed fresh from a FEN string), returns a description of that
    move. Returns None for a board with no move history (e.g. the root of
    a freshly-loaded position, where nothing was "just played").
    """
    if not board.move_stack:
        return None
    board_before = board.copy()
    last_move = board_before.pop()
    return describe_move(board_before, last_move, board)


def analyze_position(board: "chess.Board") -> PositionReport:
    """Runs all rule-based analyses and returns a structured PositionReport."""
    checks, captures = _analyze_checks_and_captures(board)
    pawn_structure = _analyze_pawn_structure(board)
    return PositionReport(
        side_to_move=_color_name(board.turn),
        move_played=_describe_last_move(board),
        checks=checks,
        captures=captures,
        attacked_pieces=_analyze_attacked_pieces(board),
        center_control=_analyze_center_control(board),
        pawn_structure=pawn_structure,
        king_safety=[
            _analyze_king_safety(board, chess.WHITE, pawn_structure),
            _analyze_king_safety(board, chess.BLACK, pawn_structure),
        ],
        material=_analyze_material(board),
    )


def generate_commentary(board: "chess.Board") -> str:
    """Runs all rule-based analyses and renders them as readable text."""
    move_desc = _describe_last_move(board)

    game_over = _game_over_message(board)
    if game_over is not None:
        return f"{move_desc} {game_over}" if move_desc else game_over

    report = analyze_position(board)
    sections = []
    if move_desc:
        sections.append(move_desc)
    sections.append(f"{report.side_to_move} to move.")

    # checks, captures, attacks
    lines = list(report.checks)
    if report.captures:
        lines.append(f"{len(report.captures)} capture(s) available: " + "; ".join(report.captures) + ".")
    if not lines:
        lines.append("No checks or captures are currently available.")
    sections.append("Checks & captures:\n" + "\n".join(f"  - {l}" for l in lines))

    # center control
    cc = report.center_control
    occ_desc = "; ".join(
        f"{sq}: {piece or 'empty'}" for sq, piece in cc.occupants.items()
    )
    lead = "White" if cc.white_score > cc.black_score else ("Black" if cc.black_score > cc.white_score else "Neither side")
    sections.append(
        "Center control:\n"
        f"  - {occ_desc}\n"
        f"  - Control score - White: {cc.white_score}, Black: {cc.black_score} ({lead} has more presence in the center)"
    )

    # attacked pieces
    if report.attacked_pieces:
        lines = []
        for ap in report.attacked_pieces:
            hanging_note = " (HANGING - no defenders)" if ap.is_hanging else ""
            lines.append(
                f"{ap.piece} on {ap.square}{hanging_note}: attacked by [{', '.join(ap.attackers)}], "
                f"defended by [{', '.join(ap.defenders) if ap.defenders else 'nothing'}]"
            )
        sections.append("Attacked pieces:\n" + "\n".join(f"  - {l}" for l in lines))
    else:
        sections.append("Attacked pieces:\n  - No pieces are currently under attack.")

    # pawn structure
    ps = report.pawn_structure
    lines = []
    for color in ("white", "black"):
        if ps.doubled[color]:
            lines.append(f"{color.capitalize()} has doubled pawns on file(s): {', '.join(ps.doubled[color])}")
        if ps.tripled[color]:
            lines.append(f"{color.capitalize()} has tripled pawns on file(s): {', '.join(ps.tripled[color])}")
        if ps.quadrupled[color]:
            lines.append(f"{color.capitalize()} has quadrupled (or more) pawns on file(s): {', '.join(ps.quadrupled[color])}")
        if ps.isolated[color]:
            lines.append(f"{color.capitalize()} has isolated pawn(s): {', '.join(ps.isolated[color])}")
        if ps.passed[color]:
            lines.append(f"{color.capitalize()} has passed pawn(s): {', '.join(ps.passed[color])}")
    if ps.open_files:
        lines.append(f"Open file(s): {', '.join(ps.open_files)}")
    if ps.half_open_files["white"]:
        lines.append(f"Half-open for White: {', '.join(ps.half_open_files['white'])}")
    if ps.half_open_files["black"]:
        lines.append(f"Half-open for Black: {', '.join(ps.half_open_files['black'])}")
    if not lines:
        lines.append("No notable pawn structure features.")
    sections.append("Pawn structure:\n" + "\n".join(f"  - {l}" for l in lines))

    # king safety
    lines = []
    for ks in report.king_safety:
        castle_rights = []
        if ks.can_castle_kingside:
            castle_rights.append("kingside")
        if ks.can_castle_queenside:
            castle_rights.append("queenside")
        rights_desc = f"can still castle {'/'.join(castle_rights)}" if castle_rights else "has lost castling rights"
        status = "castled" if ks.appears_castled else "not castled"
        shield_desc = ""
        if ks.pawn_shield_intact is not None:
            shield_desc = ", pawn shield intact" if ks.pawn_shield_intact else ", pawn shield damaged"
        open_desc = f", open/half-open file(s) near king: {', '.join(ks.open_files_adjacent)}" if ks.open_files_adjacent else ""
        lines.append(f"{ks.color} king: {status}{shield_desc}{open_desc}, {rights_desc}")
    sections.append("King safety:\n" + "\n".join(f"  - {l}" for l in lines))

    # material
    m = report.material
    if m.difference == 0:
        material_desc = "Material is even."
    else:
        leader = "White" if m.difference > 0 else "Black"
        material_desc = f"{leader} is ahead by {abs(m.difference)} point(s) of material (White: {m.white_total}, Black: {m.black_total})."
    sections.append("Material:\n  - " + material_desc)

    return "\n\n".join(sections)


if __name__ == "__main__":
    # quick manual check on the starting position and a tactical middlegame FEN
    for label, fen in [
        ("Starting position", chess.STARTING_FEN),
        ("Italian-ish middlegame", "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQ1RK1 b kq - 0 6"),
    ]:
        print("=" * 70)
        print(label)
        print("=" * 70)
        print(generate_commentary(chess.Board(fen)))
        print()