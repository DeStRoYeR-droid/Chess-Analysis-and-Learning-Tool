# CALT — Chess Analysis & Learning Tool

***Please note that the programming of this project is done on MacOS, thus some things might be MacOS specific if you want to run it on your end***

Interactive chess analysis tool built with pygame — game tree exploration, engine evaluation, and bitboard-based motif detection for position understanding.


---

### Features
- A playground for the chess-commentary generation framework that I'm working on.
- Interactive board with legal move highlighting and drag/click input
- Motif detection: pins, batteries, pawn structure, king safety
- Engine evaluation via Stockfish

### Tech Stack
pygame — rendering and input <br>
python-chess — board representation, move generation, PGN I/O <br>
Stockfish — position evaluation (UCI protocol)

---

### Progress Tracker
- [X] Generate the view 
- [X] Set up chess engine in standardised format
- [ ] Enable autoplay with stockfish
- [ ] Have the ability to import games using [FEN string](https://en.wikipedia.org/wiki/Forsyth%E2%80%93Edwards_Notation)
- [X] Apply engine + search on the game to generate a game-tree 
- [ ] Generate rule based commentary of the various nodes of the game-tree for commentary generation aspect
- [ ] Apply various search techniques to see for performance

--- 

### License
MIT — see [LICENSE](./LICENSE). Uses python-chess and Stockfish, both GPL-3.0, as external dependencies.