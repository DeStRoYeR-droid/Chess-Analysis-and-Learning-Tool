"""
Pool of Stockfish subprocesses for running independent analyses in parallel
across CPU cores.

A single StockfishEngine (stockfishWrapper.py) wraps one Stockfish process,
which can only work on one position at a time — its async methods make a
search non-blocking for the caller, but not faster. EnginePool is for actual
parallel throughput: analyzing several independent positions at once (e.g.
a batch of test FENs, or later, exploring multiple branches of a wider game
tree concurrently instead of only the single best line).

Sizing defaults are tuned for Apple Silicon laptops like the M5 MacBook Air
(10-core CPU: 4 performance + 6 efficiency cores) — 4 engine processes at
2 threads each keeps work mostly on the performance cores without
oversubscribing the machine. Tune num_engines / threads_per_engine to taste.
"""

import os

from stockfishWrapper import StockfishEngine
from engineBase import MoveEval


class EnginePool:
    def __init__(
        self,
        num_engines: int | None = None,
        threads_per_engine: int = 2,
        depth: int = 18,
        hash_mb: int = 128,
        path: str | None = None,
    ):
        """
        num_engines: how many Stockfish subprocesses to run in parallel.
                     Defaults to min(4, cpu_count) — good starting point for
                     a 10-core Apple Silicon machine; raise it if you're
                     analyzing many small/shallow positions, lower it if
                     you're running deep searches and want each engine to
                     have more threads instead.
        threads_per_engine: UCI "Threads" option per engine instance.
        depth / hash_mb / path: forwarded to each StockfishEngine.
        """
        self.num_engines = num_engines or min(4, os.cpu_count() or 4)
        self._engines = [
            StockfishEngine(path=path, depth=depth, threads=threads_per_engine, hash_mb=hash_mb)
            for _ in range(self.num_engines)
        ]

    def _engine_for(self, i: int) -> StockfishEngine:
        return self._engines[i % self.num_engines]

    def best_move_many(self, fen_strings: list[str], depth: int | None = None) -> list[str]:
        """
        Runs best_move for each FEN in parallel. Returns results in the same
        order as input.

        Each FEN is routed to one engine's *own* dedicated worker thread
        (via best_move_async), round-robin by index — this is what keeps
        two tasks from ever running concurrently on the same underlying
        Stockfish process, which python-chess's SimpleEngine does not
        support and will corrupt/cancel in-flight commands if you try.
        """
        futures = [
            self._engine_for(i).best_move_async(fen, depth)
            for i, fen in enumerate(fen_strings)
        ]
        return [f.result() for f in futures]

    def top_moves_many(self, fen_strings: list[str], k: int = 3, depth: int | None = None) -> list[list[MoveEval]]:
        """Runs top_moves for each FEN in parallel. Returns results in the same order as input."""
        futures = [
            self._engine_for(i).top_moves_async(fen, k, depth)
            for i, fen in enumerate(fen_strings)
        ]
        return [f.result() for f in futures]

    def move_tree_many(self, fen_strings: list[str], plies: int = 3, k: int = 3, depth: int | None = None) -> list:
        """Runs move_tree for each FEN in parallel. Returns results in the same order as input."""
        futures = [
            self._engine_for(i).move_tree_async(fen, plies, k, depth)
            for i, fen in enumerate(fen_strings)
        ]
        return [f.result() for f in futures]

    def close(self):
        for engine in self._engines:
            engine.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == "__main__":
    import time
    from stockfishWrapper import _load_test_cases, StockfishEngine

    cases = _load_test_cases()
    fens = [fen for fen, _, _ in cases]

    # sequential, single engine
    t0 = time.perf_counter()
    with StockfishEngine(depth=18) as sf:
        for fen in fens:
            sf.best_move(fen)
    sequential_time = time.perf_counter() - t0

    # parallel, pooled engines
    t0 = time.perf_counter()
    with EnginePool(depth=18) as pool:
        pool.best_move_many(fens)
    parallel_time = time.perf_counter() - t0

    print(f"Sequential ({len(fens)} positions, 1 engine):  {sequential_time:.2f}s")
    print(f"Parallel   ({len(fens)} positions, {min(4, os.cpu_count() or 4)} engines): {parallel_time:.2f}s")