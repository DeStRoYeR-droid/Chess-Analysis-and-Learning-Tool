import pygame
import os
import chess
from core.constants import *
from core.board import Board

THEME_FOLDER = "black-and-white-figma"

# Loading of image assets
ASSET_FOLDER = f"./assets/pieces-{THEME_FOLDER}/"

images = {}
pygame.init()

# Only png with transparent background are accepted
for filename in os.listdir(ASSET_FOLDER):
    if filename.endswith(('.png')): 
        key = os.path.splitext(filename)[0]
        images[key] = pygame.image.load(os.path.join(ASSET_FOLDER, filename))

piece_images = {
    key: pygame.transform.smoothscale(img, (SQUARE_SIZE, SQUARE_SIZE))
    for key, img in images.items()
}

# Setting up the pygame window
WIDTH = WIDTH
HEIGHT = HEIGHT
ICON = pygame.image.load(ICON_FILE)
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption(TITLE)
pygame.display.set_icon(ICON)

# Game state lives in core.board.Board - all move validation/execution is
# delegated there so it can be reused outside the GUI (autoplay, tree
# generation, etc). This file only owns rendering and input handling.
game = Board()

BOARD_ORIGIN = (BOARD_PADDING, BOARD_PADDING)  # top-left corner of the board
LIGHT_SQUARE = (240, 217, 181)
DARK_SQUARE = (181, 136, 99)
BACKGROUND = (30, 30, 30)


def draw_board(surface):
    ox, oy = BOARD_ORIGIN
    for rank in range(8):        # 0 = top row of the board
        for file in range(8):    # 0 = leftmost column
            color = LIGHT_SQUARE if (rank + file) % 2 == 0 else DARK_SQUARE
            rect = pygame.Rect(
                ox + file * SQUARE_SIZE,
                oy + rank * SQUARE_SIZE,
                SQUARE_SIZE,
                SQUARE_SIZE,
            )
            pygame.draw.rect(surface, color, rect)


def draw_pieces(surface, game: Board):
    """Blits each piece onto its square, oriented from White's perspective
    (rank 8 at the top, rank 1 at the bottom; file a on the left)."""
    ox, oy = BOARD_ORIGIN
    for square, piece in game.occupied_squares():
        file = chess.square_file(square)   # 0 (a) .. 7 (h)
        rank = chess.square_rank(square)   # 0 (rank 1) .. 7 (rank 8)
        visual_row = 7 - rank              # rank 8 drawn at the top

        key = ("w" if piece.color == chess.WHITE else "b") + piece.symbol().upper()
        image = piece_images.get(key)
        if image is None:
            continue  # asset missing for this piece - skip rather than crash

        pos = (ox + file * SQUARE_SIZE, oy + visual_row * SQUARE_SIZE)
        surface.blit(image, pos)


def square_center(square):
    """Pixel coordinates of a square's center, given its chess.Square index."""
    ox, oy = BOARD_ORIGIN
    file = chess.square_file(square)
    rank = chess.square_rank(square)
    visual_row = 7 - rank
    cx = ox + file * SQUARE_SIZE + SQUARE_SIZE // 2
    cy = oy + visual_row * SQUARE_SIZE + SQUARE_SIZE // 2
    return cx, cy


def pixel_to_square(pos):
    """Converts a mouse position to a chess.Square, or None if outside the board."""
    x, y = pos
    ox, oy = BOARD_ORIGIN
    if not (ox <= x < ox + BOARD_SIZE and oy <= y < oy + BOARD_SIZE):
        return None
    file = (x - ox) // SQUARE_SIZE
    visual_row = (y - oy) // SQUARE_SIZE
    rank = 7 - visual_row
    return chess.square(file, rank)


SELECTED_HIGHLIGHT = (246, 246, 105)
MOVE_DOT_COLOR = (60, 140, 60)


def draw_selection(surface, selected_square, target_squares):
    if selected_square is not None:
        cx, cy = square_center(selected_square)
        rect = pygame.Rect(cx - SQUARE_SIZE // 2, cy - SQUARE_SIZE // 2, SQUARE_SIZE, SQUARE_SIZE)
        highlight = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
        highlight.fill((*SELECTED_HIGHLIGHT, 120))
        surface.blit(highlight, rect.topleft)

    dot_radius = SQUARE_SIZE // 6
    for square in target_squares:
        cx, cy = square_center(square)
        pygame.draw.circle(surface, MOVE_DOT_COLOR, (cx, cy), dot_radius)


# Selection state: which square (if any) is currently clicked, and the
# legal moves available from it (kept as full Move objects, not just
# destination squares, so a click on a target can actually be played -
# this matters for promotions, where one square can have 4 legal Moves
# to it, one per promotion piece). This is UI state, not board state, so
# it stays here rather than in core.board.
selected_square = None
legal_moves_from_selection = []


def handle_click(pos):
    global selected_square, legal_moves_from_selection

    clicked = pixel_to_square(pos)
    if clicked is None:
        selected_square = None
        legal_moves_from_selection = []
        return

    # a piece is already selected - if the click lands on one of its legal
    # destinations, play the move via core.board
    if selected_square is not None:
        move = game.try_move(selected_square, clicked)
        if move is not None:
            selected_square = None
            legal_moves_from_selection = []
            return

    if clicked == selected_square:
        # clicked the already-selected square again - deselect
        selected_square = None
        legal_moves_from_selection = []
        return

    if game.is_own_piece(clicked):
        selected_square = clicked
        legal_moves_from_selection = game.legal_moves_from(clicked)
    else:
        selected_square = None
        legal_moves_from_selection = []


def main():
    running = True
    while (running):
        # Event handler
        for event in pygame.event.get():
            if (event.type == pygame.QUIT):
                running = False
                break
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                handle_click(event.pos)

        # Draw once per frame, not once per event
        screen.fill(BACKGROUND)
        draw_board(screen)
        draw_pieces(screen, game)
        target_squares = {move.to_square for move in legal_moves_from_selection}
        draw_selection(screen, selected_square, target_squares)

        # Update the display
        pygame.display.flip()

    pygame.quit()