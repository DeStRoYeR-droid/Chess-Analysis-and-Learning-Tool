"""
Abstract base class for chess engines used by CALT.

Any engine backend (Stockfish, Lc0, a custom AlphaZero-style net, etc.) should
subclass Engine and implement best_move / top_moves. This lets the rest of
CALT (GUI, tree generation, autoplay) talk to "an engine" without knowing or
caring which one is actually running underneath.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

TEST_FILE = "./test_engine.txt"

@dataclass
class MoveEval:
    move: str                  # move in UCI format, e.g. "e2e4"
    san: str                   # move in SAN format, e.g. "e4"
    score_cp: int | None       # centipawn score, from the side-to-move's perspective
    mate_in: int | None        # moves to mate, if forced mate found (None otherwise)

    def __repr__(self):
        score = f"mate in {self.mate_in}" if self.mate_in is not None else f"{self.score_cp} cp"
        return f"<{self.san} ({score})>"


class Engine(ABC):
    """
    Common interface every CALT engine backend must implement.

    Subclasses are responsible for their own process/model lifecycle
    (starting it in __init__, cleaning it up in close()).
    """

    @abstractmethod
    def best_move(self, fen_string: str, **kwargs) -> str:
        """Return the best move from the position, in UCI format (e.g. 'e2e4')."""
        raise NotImplementedError

    @abstractmethod
    def top_moves(self, fen_string: str, k: int = 3, **kwargs) -> list[MoveEval]:
        """Return the k best moves from the position, best first, with evaluations."""
        raise NotImplementedError

    def close(self):
        """Release any underlying process/resources. Override if there's cleanup to do."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def _load_test_cases(path: str = TEST_FILE) -> list[tuple[str, int, int]]:
    cases = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fen, depth, k = [part.strip() for part in line.split("|")]
            cases.append((fen, int(depth), int(k)))
    return cases