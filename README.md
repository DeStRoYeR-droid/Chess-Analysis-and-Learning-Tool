# CALT — Chess Analysis & Learning Tool

---

## UPDATE 
> A concurrent EACL submission, [*"Search-Tree-Grounded Explanations for Chess"*](https://openreview.net/forum?id=FkkemudWzf#discussion) (under review), independently proposes a closely related search-evidence + LLM-explanation architecture — validating the core design principle CALT follows.

---

***Please note that the programming of this project is done on MacOS, thus some things might be MacOS specific if you want to run it on your end***

Interactive chess analysis tool built with pygame — game tree exploration, engine evaluation, and bitboard-based motif detection for position understanding.


---

### Features
- A playground for the chess-commentary generation framework that I'm working on.
- Interactive board with legal move highlighting and drag/click input
- Motif detection: pins, batteries, pawn structure, king safety
- Engine evaluation via Stockfish

### Tech Stack
- **pygame** — rendering and input
- **python-chess** — board representation, move generation, PGN I/O
- **Stockfish** — position evaluation (UCI protocol)

---

### Progress Tracker
- [X] Generate the view 
- [X] Set up chess engine in standardised format
- [X] Have the ability to import games using [FEN string](https://en.wikipedia.org/wiki/Forsyth%E2%80%93Edwards_Notation)
- [X] Apply engine + search on the game to generate a game-tree 
- [X] Generate rule based commentary of the various nodes of the game-tree for commentary generation aspect
- [ ] Apply various search techniques to see for performance - for now it's a simple BFS on top k moves
- [ ] Compare it with the current research on chess commentary
- [ ] Develop an API for the same to make a web interface which can then send request
    - [ ] Develop a front-end to serve the same which contains the following
        - [ ] Chess board
        - [ ] Analysis button
        - [ ] Text area to present both the terminal output and analysis

--- 

### Future Prospects
- [ ] Opening books - Lot of chess commentary use opening books, currently no opening book knowledge
- [ ] Search algorithm - Iterative deepening (optional)
- [ ] Intent analysis - way advanced 

---

### License
MIT — see [LICENSE](./LICENSE). Uses python-chess and Stockfish, both GPL-3.0, as external dependencies.