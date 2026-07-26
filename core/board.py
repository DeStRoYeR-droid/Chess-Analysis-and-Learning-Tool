"""
Core board wrapper around python-chess.

This owns the actual game state and all move-validation/execution logic, so
any interface - the pygame GUI, autoplay loop, tree generation, TreeRAG
motif detection, etc. - shares the same board logic instead of each
reimplementing it. Interfaces should only handle their own concerns (e.g.
pixel <-> square coordinate math in the GUI) and delegate everything about
"is this move legal" / "what happens if I play it" to this module.
"""

import chess


class Board:
    def __init__(self, fen: str | None = None):
        self._board = chess.Board(fen) if fen else chess.Board()

    # ---- state -------------------------------------------------------

    @property
    def turn(self) -> bool:
        """chess.WHITE or chess.BLACK - whose move it currently is."""
        return self._board.turn

    def piece_at(self, square: int):
        """Returns the chess.Piece at `square`, or None if empty."""
        return self._board.piece_at(square)

    def is_own_piece(self, square: int) -> bool:
        """True if `square` holds a piece belonging to the side to move."""
        piece = self._board.piece_at(square)
        return piece is not None and piece.color == self._board.turn

    def fen(self) -> str:
        return self._board.fen()

    def is_game_over(self) -> bool:
        return self._board.is_game_over()

    def outcome(self):
        return self._board.outcome()

    # ---- move validation / execution ----------------------------------

    def legal_moves_from(self, square: int) -> list[chess.Move]:
        """All legal chess.Move objects starting at `square`."""
        return [move for move in self._board.legal_moves if move.from_square == square]

    def choose_move_to(self, moves: list[chess.Move], target_square: int) -> chess.Move | None:
        """
        Given several legal Moves landing on the same square (only happens
        with pawn promotion - one Move per promotion piece), pick which one
        to actually play. Auto-promotes to queen for now; swap this out
        later if you want a promotion-piece picker in the UI.

        Returns None if no move in `moves` lands on target_square.
        """
        matches = [m for m in moves if m.to_square == target_square]
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        return next((m for m in matches if m.promotion == chess.QUEEN), matches[0])

    def try_move(self, from_square: int, to_square: int) -> chess.Move | None:
        """
        Attempts to play the legal move from from_square to to_square
        (auto-resolving promotion choice via choose_move_to). If legal,
        plays it and returns the Move. If illegal, returns None and the
        board is left unchanged.
        """
        move = self.choose_move_to(self.legal_moves_from(from_square), to_square)
        if move is not None:
            self._board.push(move)
        return move

    def push(self, move: chess.Move) -> None:
        """Plays an already-constructed Move directly (e.g. from an engine)."""
        self._board.push(move)

    def pop(self) -> chess.Move:
        """Undoes the last move played, returning it."""
        return self._board.pop()

    def reset(self) -> None:
        self._board.reset()

    def set_fen(self, fen: str) -> None:
        self._board.set_fen(fen)

    # ---- iteration ------------------------------------------------------

    def occupied_squares(self):
        """Yields (square, piece) for every occupied square on the board."""
        for square in chess.SQUARES:
            piece = self._board.piece_at(square)
            if piece is not None:
                yield square, piece

    # ---- escape hatch -----------------------------------------------------

    @property
    def raw(self) -> chess.Board:
        """The underlying python-chess Board, for anything not yet wrapped
        here (e.g. PGN export, SAN conversion). Prefer adding a method above
        over reaching for this directly from calling code where practical."""
        return self._board