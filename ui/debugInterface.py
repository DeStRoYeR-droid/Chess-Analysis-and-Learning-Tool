"""
Terminal debug interface for CALT.

Flow:
  1. You provide a FEN (a position you've already analyzed yourself) and a
     move in standard algebraic notation (SAN, e.g. "Nf3", "e4", "Qxf7") -
     the move you've decided on for that position.
  2. The input position and the position after your move are both printed
     to the terminal.
  3. Stockfish computes its own best move from the *original* (pre-move)
     FEN, and reports whether it matches your move (isOptimal).
  4. Two move trees are generated with StockfishEngine.move_tree
     (depth=22, plies=5, top_k=5):
       - "player_line_tree", rooted at the position after YOUR move
       - "engine_line_tree", rooted at the position after the ENGINE's
         best move
     (If your move IS the engine's best move, both trees start from the
     same position - both are still generated independently.)
  5. Every node in both trees gets rule-based commentary
     (core.ruleBasedCommentaryGeneration.generate_commentary), computed on
     that node's actual resulting position - not just its move.
  6. The whole thing is dumped as JSON to the terminal.

Run from the project root: python3 ui/debugInterface.py
"""

import json
import sys

import chess

from engine.stockfishWrapper import StockfishEngine, TreeNode
from core.ruleBasedCommentaryGeneration import generate_commentary

STOCKFISH_DEPTH = 18
TREE_PLIES = 3
TOP_K = 3


def print_board(board: chess.Board, label: str) -> None:
    print(f"\n{label}")
    print(board.unicode(borders=True, empty_square="."))
    print(f"FEN: {board.fen()}")


def read_fen() -> chess.Board:
    while True:
        raw = input("Enter FEN: ").strip()
        try:
            return chess.Board(raw)
        except ValueError as e:
            print(f"  Invalid FEN ({e}). Try again.")


def read_move(board: chess.Board) -> chess.Move:
    while True:
        raw = input("Enter your move (SAN, e.g. 'Nf3'): ").strip()
        try:
            return board.parse_san(raw)
        except ValueError as e:
            print(f"  '{raw}' is not legal in this position ({e}). Try again.")


def serialize_tree(node: TreeNode, board: chess.Board) -> dict:
    """
    Recursively serializes a TreeNode into a JSON-friendly dict, attaching
    rule-based commentary computed on each node's actual resulting
    position - reconstructed by replaying node.move_eval.move onto `board`
    as we descend, since TreeNode itself only stores the move, not the FEN.
    """
    if node.move_eval is None:
        # synthetic root node (move_tree()'s entry point) - `board` passed
        # in already IS this node's position, no move to replay.
        return {
            "san": None,
            "move_uci": None,
            "fen": board.fen(),
            "eval_cp": None,
            "mate_in": None,
            "eval_delta_cp": None,
            "commentary": generate_commentary(board),
            "children": [serialize_tree(child, board) for child in node.children],
        }

    next_board = board.copy()
    next_board.push(chess.Move.from_uci(node.move_eval.move))

    return {
        "san": node.san,
        "move_uci": node.move_eval.move,
        "fen": next_board.fen(),
        "eval_cp": node.eval_cp_white(),
        "mate_in": node.move_eval.mate_in,
        "eval_delta_cp": node.eval_delta_cp(),
        "commentary": generate_commentary(next_board),
        "children": [serialize_tree(child, next_board) for child in node.children],
    }


def main():
    board = read_fen()
    print_board(board, "Input position")

    player_move = read_move(board)
    player_move_san = board.san(player_move)

    board_after_player = board.copy()
    board_after_player.push(player_move)
    print_board(board_after_player, f"Position after your move ({player_move_san})")

    with StockfishEngine(depth=STOCKFISH_DEPTH) as sf:
        engine_best_uci = sf.best_move(board.fen())
        engine_best_move = chess.Move.from_uci(engine_best_uci)
        engine_best_san = board.san(engine_best_move)
        is_optimal = (player_move.uci() == engine_best_uci)

        print(
            f"\nEngine's best move: {engine_best_san} "
            f"({'MATCHES your move' if is_optimal else 'differs from your move'})"
        )

        board_after_engine = board.copy()
        board_after_engine.push(engine_best_move)

        print(f"Building move tree for your line (plies={TREE_PLIES}, k={TOP_K}, depth={STOCKFISH_DEPTH})...")
        player_tree = sf.move_tree(board_after_player.fen(), plies=TREE_PLIES, k=TOP_K, depth=STOCKFISH_DEPTH)

        print("Building move tree for the engine's line...")
        engine_tree = sf.move_tree(board_after_engine.fen(), plies=TREE_PLIES, k=TOP_K, depth=STOCKFISH_DEPTH)

    output = {
        "input_fen": board.fen(),
        "player_move": {"san": player_move_san, "uci": player_move.uci()},
        "engine_best_move": {"san": engine_best_san, "uci": engine_best_uci},
        "is_optimal": is_optimal,
        "player_line_tree": serialize_tree(player_tree, board_after_player),
        "engine_line_tree": serialize_tree(engine_tree, board_after_engine),
    }

    print("\n" + "=" * 70)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()