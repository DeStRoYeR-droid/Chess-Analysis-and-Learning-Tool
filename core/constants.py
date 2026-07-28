# GUI configutations
WIDTH = 1200
HEIGHT = 800
TITLE = "Chess Analysis and Learning Tool"
ICON_FILE = "./assets/calt-logo.png"

# Board layout
BOARD_PADDING = 50  # distance from the top and left edges of the window
BOARD_SIZE = 500  # depict the board size
SQUARE_SIZE = BOARD_SIZE // 8
BOARD_SIZE = SQUARE_SIZE * 8  # re-snap so 8 squares tile it exactly, no leftover pixels

# For tree generation
STOCKFISH_DEPTH = 18
TREE_PLIES = 5
TOP_K = 5           # 5 x 5 => 3125 nodes in the tree.

# LLM Specific
PROMPT_FOLDER_PATH = "../core/prompts"
LLM_MODEL = "gemma-4-e4b-it-qat-OptiQ-4bit"
