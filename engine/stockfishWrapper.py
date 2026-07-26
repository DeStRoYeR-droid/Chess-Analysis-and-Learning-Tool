"""
Thin wrapper around Stockfish via python-chess's UCI engine interface.

Usage:
    engine = StockfishEngine()
    engine.best_move("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    engine.top_moves(fen, k=3)
    engine.close()

Or as a context manager:
    with StockfishEngine() as engine:
        engine.best_move(fen)
"""

import shutil
import concurrent.futures

import chess
import chess.engine

from engineBase import Engine, MoveEval, _load_test_cases

from dataclasses import dataclass, field


# Common Homebrew install locations, checked in order if PATH lookup fails.
_FALLBACK_PATHS = [
    "/opt/homebrew/bin/stockfish",  # Apple Silicon (Development platform used by me)
    "/usr/local/bin/stockfish",     # Intel Mac (For anybody debugging on Intel mac)
]


def _find_stockfish() -> str:
    path = shutil.which("stockfish")
    if path:
        return path
    for candidate in _FALLBACK_PATHS:
        if shutil.os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(
        "Could not locate the stockfish binary. Install it with `brew install "
        "stockfish`, or pass an explicit path to StockfishEngine(path=...)."
    )

@dataclass
class TreeNode:
    san: str | None                 # None only for the synthetic root node
    move_eval: MoveEval | None      # None only for the synthetic root node
    parent: "TreeNode | None" = None
    mover_is_white: bool | None = None   # who played this node's move (None for root)
    children: list["TreeNode"] = field(default_factory=list)

    def eval_cp_white(self) -> int | None:
        """
        This node's centipawn evaluation normalized to White's perspective.

        move_eval.score_cp is POV of whoever *made* this move, which flips
        every ply — so it can't be compared directly across nodes at
        different depths. This normalizes it so parent and child evals live
        on the same scale.
        """
        if self.move_eval is None or self.move_eval.score_cp is None:
            return None
        return self.move_eval.score_cp if self.mover_is_white else -self.move_eval.score_cp

    def eval_delta_cp(self) -> int | None:
        """
        Centipawn swing from the parent node's evaluation to this node's,
        both normalized to White's perspective. This is the "context passed
        from node to node" — how much the position's assessment changed as
        a result of this move. None if either side is a forced-mate score,
        or if the parent has no evaluation of its own to compare against
        (e.g. this is a direct child of the tree's root).

        Later, this is what rule-based commentary will threshold against
        (e.g. "drop of 150+ cp for the mover = inaccuracy/blunder").
        """
        if self.parent is None:
            return None
        my_eval = self.eval_cp_white()
        parent_eval = self.parent.eval_cp_white()
        if my_eval is None or parent_eval is None:
            return None
        return my_eval - parent_eval


def _format_eval(node: "TreeNode") -> str:
    me = node.move_eval
    if me is None:
        return ""
    if me.mate_in is not None:
        score = f"#{me.mate_in}"
    else:
        score = f"{node.eval_cp_white():+d}cp"
    delta = node.eval_delta_cp()
    return f"  ({score}, {delta:+d}Δ)" if delta is not None else f"  ({score})"


def print_tree(node: "TreeNode", indent: int = 0) -> None:
    """
    Pretty-prints a move tree in the CALT tree-branch style, with eval and
    (where available) the centipawn swing from the parent node, e.g.:

        e4    (+30cp)
        |    e5    (+25cp, -5Δ)
        |    |    Nf3    (+35cp, +10Δ)
        |    |    |    Nf6    (+20cp, -15Δ)
        |    |    d3    (-10cp, -45Δ)
    """
    prefix = "|    " * indent
    for child in node.children:
        print(f"{prefix}{child.san}{_format_eval(child)}")
        if child.children:
            print_tree(child, indent + 1)
 
 
class StockfishEngine(Engine):
    def __init__(self, path: str | None = None, depth: int = 18, threads: int = 4, hash_mb: int = 256):
        """
        path: explicit path to the stockfish binary. Auto-detected via PATH / brew
              default locations if not given.
        depth: default search depth used by best_move / top_moves.
        threads / hash_mb: passed to Stockfish's UCI options.
        """
        self.path = path or _find_stockfish()
        self.depth = depth
        self._engine = chess.engine.SimpleEngine.popen_uci(self.path)
        self._engine.configure({"Threads": threads, "Hash": hash_mb})
        # Single background worker: a Stockfish subprocess can only run one
        # analysis at a time anyway, so this doesn't add throughput — it
        # exists purely so callers (e.g. a pygame main loop) don't block
        # waiting on the result. For real parallel throughput across
        # independent positions, use EnginePool instead (engine_pool.py).
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
 
    def best_move(self, fen_string: str, depth: int | None = None) -> str:
        """Returns the best move from the position, in UCI format (e.g. 'e2e4')."""
        board = chess.Board(fen_string)
        if board.is_game_over():
            raise ValueError(f"Position is already game over ({board.outcome()}), no move to make.")
        result = self._engine.play(board, chess.engine.Limit(depth=depth or self.depth))
        return result.move.uci()
 
    def top_moves(self, fen_string: str, k: int = 3, depth: int | None = None) -> list[MoveEval]:
        """Returns the k best moves from the position, best first, with evaluations."""
        board = chess.Board(fen_string)
        if board.is_game_over():
            # no legal moves to analyse (checkmate/stalemate/etc.)
            return []
        infos = self._engine.analyse(
            board,
            chess.engine.Limit(depth=depth or self.depth),
            multipv=k,
        )
        # analyse() returns a single dict if multipv=1, else a list — normalize to list.
        if isinstance(infos, dict):
            infos = [infos]
 
        results = []
        for info in infos:
            move = info["pv"][0]
            score = info["score"].pov(board.turn)  # perspective of side to move
            results.append(
                MoveEval(
                    move=move.uci(),
                    san=board.san(move),
                    score_cp=score.score(),        # None if mate
                    mate_in=score.mate(),          # None if not mate
                )
            )
        return results
 
    def close(self):
        self._executor.shutdown(wait=True)
        self._engine.quit()

    # ---- non-blocking variants ------------------------------------------
    #
    # These submit the same blocking work to a background thread and return
    # a concurrent.futures.Future immediately, instead of blocking the
    # calling thread until Stockfish responds. Intended for use from the
    # pygame main loop so a search-in-progress never freezes rendering.
    #
    # Usage in a pygame loop:
    #   future = sf.best_move_async(fen)
    #   ...later, once per frame...
    #   if future.done():
    #       move = future.result()
    #
    # Or with a callback instead of polling:
    #   future.add_done_callback(lambda f: handle_move(f.result()))
    #   (note: the callback fires on the background thread, not the main
    #   thread — if you touch pygame/GUI state in it, hand the result off
    #   via a queue rather than acting on it directly there)

    def best_move_async(self, fen_string: str, depth: int | None = None) -> "concurrent.futures.Future[str]":
        return self._executor.submit(self.best_move, fen_string, depth)

    def top_moves_async(self, fen_string: str, k: int = 3, depth: int | None = None) -> "concurrent.futures.Future[list[MoveEval]]":
        return self._executor.submit(self.top_moves, fen_string, k, depth)

    def move_tree_async(self, fen_string: str, plies: int = 3, k: int = 3, depth: int | None = None) -> "concurrent.futures.Future[TreeNode]":
        return self._executor.submit(self.move_tree, fen_string, plies, k, depth)
 
    def move_tree(self, fen_string: str, plies: int = 3, k: int = 3, depth: int | None = None) -> "TreeNode":
        """
        Build a shallow move tree from the position.
 
        At each node the top-k candidate moves are computed. Only the best
        candidate (index 0) is expanded further, down to `plies` levels deep;
        the remaining k-1 candidates are included as unexpanded leaves at
        that same depth (siblings of the expanded move, one node deeper than
        their parent).
 
        Returns a TreeNode you can print with print_tree(), or walk manually.
        """
        board = chess.Board(fen_string)
        root = TreeNode(san=None, move_eval=None)
        self._populate_children(root, board, plies, k, depth)
        return root

    def _populate_children(self, parent_node: "TreeNode", board: "chess.Board", plies: int, k: int, depth: int | None) -> None:
        if plies <= 0:
            return

        candidates = self.top_moves(board.fen(), k=k, depth=depth)
        for i, move_eval in enumerate(candidates):
            child = TreeNode(
                san=move_eval.san,
                move_eval=move_eval,
                parent=parent_node,
                mover_is_white=(board.turn == chess.WHITE),
            )
            parent_node.children.append(child)

            if i == 0 and plies > 1:
                next_board = board.copy()
                next_board.push(chess.Move.from_uci(move_eval.move))
                if not next_board.is_game_over():
                    self._populate_children(child, next_board, plies - 1, k, depth)
 
 
 
if __name__ == "__main__":
    cases = _load_test_cases()[:10]
    with StockfishEngine() as sf:
        for fen, depth, k in cases:
            print ("=" * 60)
            print (f"FEN: {fen}")
            print (f"best_move: {sf.best_move(fen, depth=depth)}")
            print (f"top_moves (k={k}):")
            for mv in sf.top_moves(fen, k=k, depth=depth):
                print(f"  {mv}")
            print ("move_tree (plies=3):")
            tree = sf.move_tree(fen, plies=3, k=k, depth=depth)
            print_tree(tree)
            print ("\n\n\n")