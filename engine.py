#!/usr/bin/env python3
import sys
import chess

# UCI "Depth" option bounds
DEFAULT_MAX_DEPTH = 4
MAX_ALLOWED_DEPTH = 20

MATE_SCORE_THRESHOLD = 90000
MATE_VALUE = 99999

# Base piece values in centipawns
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}

STARTING_PIECE_MATERIAL = (
    2 * PIECE_VALUES[chess.KNIGHT]
    + 2 * PIECE_VALUES[chess.BISHOP]
    + 2 * PIECE_VALUES[chess.ROOK]
    + PIECE_VALUES[chess.QUEEN]
)

PASSED_PAWN_BONUS = [0, 5, 15, 30, 60, 120, 240, 0]

DOUBLED_PAWN_PENALTY_MG = 15
DOUBLED_PAWN_PENALTY_EG = 30

ISOLATED_PAWN_PENALTY_MG = 20
ISOLATED_PAWN_PENALTY_EG = 40

# Piece-Square Tables (White's perspective)
PAWN_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0
]

KNIGHT_TABLE = [
   -50,-40,-30,-30,-30,-30,-40,-50,
   -40,-20,  0,  0,  0,  0,-20,-40,
   -30,  0, 20, 15, 15, 20,  0,-30,
   -30,  5, 15, 15, 15, 15,  5,-30,
   -30,  0, 15, 15, 15, 15,  0,-30,
   -30,  5, 20, 15, 15, 20,  5,-30,
   -40,-20,  0,  5,  5,  0,-20,-40,
   -50,-40,-30,-30,-30,-30,-40,-50
]

BISHOP_TABLE = [
   -20,-10,-10,-10,-10,-10,-10,-20,
   -10,  0,  0,  0,  0,  0,  0,-10,
   -10,  0,  5, 10, 10,  5,  0,-10,
   -10,  5,  5, 10, 10,  5,  5,-10,
   -10,  0, 10, 10, 10, 10,  0,-10,
   -10, 10, 10, 10, 10, 10, 10,-10,
   -10,  5,  0,  0,  0,  0,  5,-10,
   -20,-10,-10,-10,-10,-10,-10,-20
]

ROOK_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10, 10, 10, 10, 10,  5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
     0,  0,  0,  5,  5,  0,  0,  0
]

QUEEN_MIDDLEGAME_TABLE = [
   -20,-10,-10, -5, -5,-10,-10,-20,
   -10,  0,  0,  0,  0,  0,  0,-10,
   -10,  0,  5,  5,  5,  5,  0,-10,
    -5,  0,  5,  5,  5,  5,  0, -5,
     0,  0,  5,  5,  5,  5,  0, -5,
   -10,  5,  5,  5,  5,  5,  0,-10,
   -10, -5, -5, -5, -5, -5, -5,-10, 
   -20,-15,-15, 10, 10,-15,-15,-20  
]

QUEEN_ENDGAME_TABLE = [
   -20,-10,-10, -5, -5,-10,-10,-20,
   -10,  0,  0,  0,  0,  0,  0,-10,
   -10,  0,  5,  5,  5,  5,  0,-10,
    -5,  0,  5,  5,  5,  5,  0, -5,
     0,  0,  5,  5,  5,  5,  0, -5,
   -10,  5,  5,  5,  5,  5,  0,-10,
   -10,  0,  5,  0,  0,  0,  0,-10,
   -20,-10,-10, -5, -5,-10,-10,-20
]

KING_MIDDLEGAME_TABLE = [
   -30,-40,-40,-50,-50,-40,-40,-30,
   -30,-40,-40,-50,-50,-40,-40,-30,
   -30,-40,-40,-50,-50,-40,-40,-30,
   -30,-40,-40,-50,-50,-40,-40,-30,
   -20,-30,-30,-40,-40,-30,-30,-20,
   -10,-20,-20,-20,-20,-20,-20,-10,
    20, 20,  0,  0,  0,  0, 20, 20,
    20, 30, 10,  0,  0, 10, 30, 20
]

KING_ENDGAME_TABLE = [
   -50,-40,-30,-20,-20,-30,-40,-50,
   -30,-20,-10,  0,  0,-10,-20,-30,
   -30,-10, 20, 30, 30, 20,-10,-30,
   -30,-10, 30, 40, 40, 30,-10,-30,
   -30,-10, 30, 40, 40, 30,-10,-30,
   -30,-10, 20, 30, 30, 20,-10,-30,
   -30,-30,  0,  0,  0,  0,-30,-30,
   -50,-30,-30,-30,-30,-30,-30,-50
]

BISHOP_PAIR_BONUS = 30
ROOK_OPEN_FILE_BONUS = 20
ROOK_SEMI_OPEN_FILE_BONUS = 10

def safe_flush():
    try:
        sys.stdout.flush()
    except (BrokenPipeError, IOError):
        sys.exit(0)

def is_endgame(board: chess.Board) -> bool:
    queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    if queens == 0:
        return True
    
    minors_majors = (
        len(board.pieces(chess.KNIGHT, chess.WHITE)) + len(board.pieces(chess.KNIGHT, chess.BLACK)) +
        len(board.pieces(chess.BISHOP, chess.WHITE)) + len(board.pieces(chess.BISHOP, chess.BLACK)) +
        len(board.pieces(chess.ROOK, chess.WHITE)) + len(board.pieces(chess.ROOK, chess.BLACK))
    )
    return minors_majors <= 2

def is_passed_pawn(board: chess.Board, square: int, color: chess.Color) -> bool:
    file_idx = chess.square_file(square)
    rank_idx = chess.square_rank(square)
    enemy_color = not color

    adjacent_files = [f for f in [file_idx - 1, file_idx, file_idx + 1] if 0 <= f <= 7]

    for f in adjacent_files:
        for r in range(8):
            if (color == chess.WHITE and r > rank_idx) or (color == chess.BLACK and r < rank_idx):
                target_sq = chess.square(f, r)
                piece = board.piece_at(target_sq)
                if piece and piece.piece_type == chess.PAWN and piece.color == enemy_color:
                    return False
    return True

def evaluate_pawn_structure(board: chess.Board, in_endgame: bool) -> int:
    score = 0
    doubled_penalty = DOUBLED_PAWN_PENALTY_EG if in_endgame else DOUBLED_PAWN_PENALTY_MG
    isolated_penalty = ISOLATED_PAWN_PENALTY_EG if in_endgame else ISOLATED_PAWN_PENALTY_MG

    for color in [chess.WHITE, chess.BLACK]:
        pawns = board.pieces(chess.PAWN, color)
        pawn_score = 0

        for sq in pawns:
            file_idx = chess.square_file(sq)
            rank_idx = chess.square_rank(sq)
            relative_rank = rank_idx if color == chess.WHITE else 7 - rank_idx

            if is_passed_pawn(board, sq, color):
                pawn_score += PASSED_PAWN_BONUS[relative_rank]

            pawns_on_file = sum(1 for p_sq in pawns if chess.square_file(p_sq) == file_idx)
            if pawns_on_file > 1:
                pawn_score -= doubled_penalty

            adjacent_files = [f for f in [file_idx - 1, file_idx + 1] if 0 <= f <= 7]
            has_neighbors = any(any(chess.square_file(p_sq) == adj_f for p_sq in pawns) for adj_f in adjacent_files)
            if not has_neighbors:
                pawn_score -= isolated_penalty

        if color == chess.WHITE:
            score += pawn_score
        else:
            score -= pawn_score

    return score

def evaluate_king_safety(board: chess.Board, king_sq: int, color: chess.Color) -> int:
    safety_score = 0
    file_idx = chess.square_file(king_sq)
    rank_idx = chess.square_rank(king_sq)

    shield_rank = rank_idx + 1 if color == chess.WHITE else rank_idx - 1
    if 0 <= shield_rank <= 7:
        adjacent_files = [f for f in [file_idx - 1, file_idx, file_idx + 1] if 0 <= f <= 7]
        for f in adjacent_files:
            sq = chess.square(f, shield_rank)
            piece = board.piece_at(sq)
            if piece and piece.piece_type == chess.PAWN and piece.color == color:
                safety_score += 15
            else:
                safety_score -= 20

    pawns_on_file = sum(
        1 for r in range(8)
        if (p := board.piece_at(chess.square(file_idx, r))) and p.piece_type == chess.PAWN
    )
    if pawns_on_file == 0:
        safety_score -= 35
    elif not any(
        (p := board.piece_at(chess.square(file_idx, r))) and p.piece_type == chess.PAWN and p.color == color
        for r in range(8)
    ):
        safety_score -= 20

    return safety_score

def evaluate_rook_files(board: chess.Board) -> int:
    score = 0
    for color in (chess.WHITE, chess.BLACK):
        for rook_sq in board.pieces(chess.ROOK, color):
            file_idx = chess.square_file(rook_sq)

            any_pawn_on_file = any(
                (p := board.piece_at(chess.square(file_idx, r))) and p.piece_type == chess.PAWN
                for r in range(8)
            )
            own_pawn_on_file = any(
                (p := board.piece_at(chess.square(file_idx, r))) and p.piece_type == chess.PAWN and p.color == color
                for r in range(8)
            )

            if not any_pawn_on_file:
                bonus = ROOK_OPEN_FILE_BONUS
            elif not own_pawn_on_file:
                bonus = ROOK_SEMI_OPEN_FILE_BONUS
            else:
                bonus = 0

            score += bonus if color == chess.WHITE else -bonus

    return score

def get_pst_value(piece_type: int, square: int, color: chess.Color, in_endgame: bool) -> int:
    if piece_type == chess.PAWN:
        table = PAWN_TABLE
    elif piece_type == chess.KNIGHT:
        table = KNIGHT_TABLE
    elif piece_type == chess.BISHOP:
        table = BISHOP_TABLE
    elif piece_type == chess.ROOK:
        table = ROOK_TABLE
    elif piece_type == chess.QUEEN:
        table = QUEEN_ENDGAME_TABLE if in_endgame else QUEEN_MIDDLEGAME_TABLE
    elif piece_type == chess.KING:
        table = KING_ENDGAME_TABLE if in_endgame else KING_MIDDLEGAME_TABLE
    else:
        return 0

    sq = square if color == chess.WHITE else chess.square_mirror(square)
    return table[sq]

def evaluate_hanging_pieces(board: chess.Board) -> int:
    score = 0
    for square, piece in board.piece_map().items():
        if piece.piece_type == chess.KING:
            continue

        attackers = len(board.attackers(not piece.color, square))
        defenders = len(board.attackers(piece.color, square))

        if attackers > defenders:
            loss = PIECE_VALUES[piece.piece_type] // 3
            if piece.color == chess.WHITE:
                score -= loss
            else:
                score += loss

    return score

def evaluate_board(board: chess.Board, ply: int = 0) -> int:
    if board.is_checkmate():
        return -(MATE_VALUE - ply)
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    score = 0
    in_endgame = is_endgame(board)

    score += evaluate_hanging_pieces(board)

    material_balance = 0
    for square, piece in board.piece_map().items():
        val = PIECE_VALUES[piece.piece_type] + get_pst_value(
            piece.piece_type, square, piece.color, in_endgame
        )
        score += val if piece.color == chess.WHITE else -val
        material_balance += PIECE_VALUES[piece.piece_type] if piece.color == chess.WHITE else -PIECE_VALUES[piece.piece_type]

    if material_balance > 300:
        black_piece_material = sum(
            PIECE_VALUES[pt] * len(board.pieces(pt, chess.BLACK))
            for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        )
        score += (STARTING_PIECE_MATERIAL - black_piece_material) // 50
    elif material_balance < -300:
        white_piece_material = sum(
            PIECE_VALUES[pt] * len(board.pieces(pt, chess.WHITE))
            for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        )
        score -= (STARTING_PIECE_MATERIAL - white_piece_material) // 50

    score += evaluate_pawn_structure(board, in_endgame)

    if len(board.pieces(chess.BISHOP, chess.WHITE)) >= 2:
        score += BISHOP_PAIR_BONUS
    if len(board.pieces(chess.BISHOP, chess.BLACK)) >= 2:
        score -= BISHOP_PAIR_BONUS

    score += evaluate_rook_files(board)

    if not in_endgame:
        white_king_sq = board.king(chess.WHITE)
        black_king_sq = board.king(chess.BLACK)

        if white_king_sq is not None and black_king_sq is not None:
            w_safety = evaluate_king_safety(board, white_king_sq, chess.WHITE)
            b_safety = evaluate_king_safety(board, black_king_sq, chess.BLACK)
            score += w_safety
            score -= b_safety

    return score if board.turn == chess.WHITE else -score

def quiescence_search(board: chess.Board, alpha: int, beta: int, ply: int = 0) -> int:
    stand_pat = evaluate_board(board, ply)

    if stand_pat >= beta:
        return beta
    if stand_pat > alpha:
        alpha = stand_pat

    for move in board.legal_moves:
        if board.is_capture(move) or move.promotion:
            board.push(move)
            score = -quiescence_search(board, -beta, -alpha, ply + 1)
            board.pop()

            if score >= beta:
                return beta
            if score > alpha:
                alpha = score

    return alpha

def negamax(board: chess.Board, depth: int, alpha: int, beta: int, ply: int = 0) -> int:
    if board.is_repetition(2):
        return 0

    if board.is_game_over():
        return evaluate_board(board, ply)

    if depth == 0:
        return quiescence_search(board, alpha, beta, ply)

    max_score = -float('inf')

    for move in board.legal_moves:
        board.push(move)
        score = -negamax(board, depth - 1, -beta, -alpha, ply + 1)
        board.pop()

        if score > max_score:
            max_score = score
        if score > alpha:
            alpha = score
        if alpha >= beta:
            break

    return max_score

def get_best_move(board: chess.Board, max_depth: int = DEFAULT_MAX_DEPTH):
    best_move = None
    best_score = -float('inf')
    
    alpha = -float('inf')
    beta = float('inf')

    for depth in range(1, max_depth + 1):
        best_move_this_depth = None
        best_score_this_depth = -float('inf')
