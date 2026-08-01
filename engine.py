#!/usr/bin/env python3
import sys
import chess

# Base piece values in centipawns
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}

# Balanced passed pawn scaling (Index 0 = Rank 1, Index 6 = Rank 7)
PASSED_PAWN_BONUS = [0, 5, 15, 30, 60, 120, 240, 0]

# Structural penalties (centipawns)
DOUBLED_PAWN_PENALTY_MG = 15
DOUBLED_PAWN_PENALTY_EG = 30

ISOLATED_PAWN_PENALTY_MG = 20
ISOLATED_PAWN_PENALTY_EG = 40

# Mini Opening Book for instant responses in the opening
OPENING_BOOK = {
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR": "e2e4",  # Start pos -> 1. e4
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR": "c7c5",  # 1. e4 -> 1... c5 (Sicilian)
    "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR": "g8f6",  # 1. d4 -> 1... Nf6
}

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
   -30,  0, 10, 15, 15, 10,  0,-30,
   -30,  5, 15, 20, 20, 15,  5,-30,
   -30,  0, 15, 20, 20, 15,  0,-30,
   -30,  5, 10, 15, 15, 10,  5,-30,
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

QUEEN_TABLE = [
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

def is_endgame(board: chess.Board) -> bool:
    """Detects if position is in endgame phase."""
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
    """Checks if a pawn is passed."""
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
    """Evaluates pawn structure features."""
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

        score += pawn_score if color == board.turn else -pawn_score

    return score

def evaluate_king_safety(board: chess.Board, king_sq: int, color: chess.Color) -> int:
    """Evaluates Pawn Shield and file exposure for Middlegame King safety."""
    safety_score = 0
    file_idx = chess.square_file(king_sq)
    rank_idx = chess.square_rank(king_sq)

    # 1. Pawn Shield
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

    # 2. File Exposure
    pawns_on_file = sum(
        1 for r in range(8)
        if (p := board.piece_at(chess.square(file_idx, r))) and p.piece_type == chess.PAWN
    )
    if pawns_on_file == 0:
        safety_score -= 35  # Open file
    elif not any(
        (p := board.piece_at(chess.square(file_idx, r))) and p.piece_type == chess.PAWN and p.color == color
        for r in range(8)
    ):
        safety_score -= 20  # Semi-open file

    return safety_score

def get_pst_value(piece_type: int, square: int, color: chess.Color, in_endgame: bool) -> int:
    """Fetches positional bonus/penalty for a piece on a given square."""
    if piece_type == chess.PAWN:
        table = PAWN_TABLE
    elif piece_type == chess.KNIGHT:
        table = KNIGHT_TABLE
    elif piece_type == chess.BISHOP:
        table = BISHOP_TABLE
    elif piece_type == chess.ROOK:
        table = ROOK_TABLE
    elif piece_type == chess.QUEEN:
        table = QUEEN_TABLE
    elif piece_type == chess.KING:
        table = KING_ENDGAME_TABLE if in_endgame else KING_MIDDLEGAME_TABLE
    else:
        return 0

    sq = square if color == chess.WHITE else chess.square_mirror(square)
    return table[sq]

def get_mobility_score(board: chess.Board) -> int:
    """Calculates piece mobility (1 centipawn per legal move square available)."""
    mobility_score = 0
    turn = board.turn

    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None or piece.piece_type == chess.KING:
            continue
            
        attacks = len(board.attacks(sq))
        mobility_score += attacks if piece.color == turn else -attacks

    return mobility_score

def evaluate_board(board: chess.Board) -> int:
    """Complete evaluation using Material, PSTs, Mobility, Pawn Structure, and King Safety."""
    if board.is_checkmate():
        return -99999
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    score = 0
    in_endgame = is_endgame(board)
    turn = board.turn

    # 1. Material + Piece-Square Tables
    for square, piece in board.piece_map().items():
        val = PIECE_VALUES[piece.piece_type] + get_pst_value(piece.piece_type, square, piece.color, in_endgame)
        score += val if piece.color == turn else -val

    # 2. Piece Mobility
    score += get_mobility_score(board)

    # 3. Pawn Structure
    score += evaluate_pawn_structure(board, in_endgame)

    # 4. King Safety
    if not in_endgame:
        white_king_sq = board.king(chess.WHITE)
        black_king_sq = board.king(chess.BLACK)

        if white_king_sq is not None and black_king_sq is not None:
            w_safety = evaluate_king_safety(board, white_king_sq, chess.WHITE)
            b_safety = evaluate_king_safety(board, black_king_sq, chess.BLACK)
            
            score += w_safety if turn == chess.WHITE else -w_safety
            score -= b_safety if turn == chess.WHITE else -b_safety

    return score

def score_move(board: chess.Board, move: chess.Move) -> int:
    """Assigns priority scores to moves for faster Alpha-Beta pruning."""
    if board.is_capture(move):
        victim = board.piece_at(move.to_square)
        attacker = board.piece_at(move.from_square)
        victim_val = PIECE_VALUES[victim.piece_type] if victim else 100
        attacker_val = PIECE_VALUES[attacker.piece_type] if attacker else 100
        return 1000 + (victim_val - attacker_val)

    if board.gives_check(move):
        return 500

    to_sq = move.to_square
    if to_sq in [chess.E4, chess.D4, chess.E5, chess.D5]:
        return 100
    if to_sq in [chess.F3, chess.C3, chess.F6, chess.C6]:
        return 50

    return 0

def order_moves(board: chess.Board) -> list:
    """Sorts legal moves so Alpha-Beta prunes useless branches faster."""
    moves = list(board.legal_moves)
    moves.sort(key=lambda m: score_move(board, m), reverse=True)
    return moves

def quiescence_search(board: chess.Board, alpha: int, beta: int) -> int:
    """Searches captures until a stable position is reached."""
    stand_pat = evaluate_board(board)
    
    if stand_pat >= beta:
        return beta
    if alpha < stand_pat:
        alpha = stand_pat

    for move in board.legal_moves:
        if board.is_capture(move):
            board.push(move)
            score = -quiescence_search(board, -beta, -alpha)
            board.pop()

            if score >= beta:
                return beta
            if score > alpha:
                alpha = score

    return alpha

def negamax(board: chess.Board, depth: int, alpha: int, beta: int) -> int:
    """Negamax search algorithm with Alpha-Beta pruning and move ordering."""
    if board.is_game_over():
        return evaluate_board(board)

    if depth == 0:
        return quiescence_search(board, alpha, beta)

    max_score = -float('inf')

    for move in order_moves(board):
        board.push(move)
        score = -negamax(board, depth - 1, -beta, -alpha)
        board.pop()

        if score > max_score:
            max_score = score
        if score > alpha:
            alpha = score
        if alpha >= beta:
            break

    return max_score

def get_best_move(board: chess.Board, depth: int = 3) -> chess.Move:
    """Finds best move using Negamax search or opening book."""
    board_fen_position = board.fen().split(" ")[0]
    if board_fen_position in OPENING_BOOK:
        return chess.Move.from_uci(OPENING_BOOK[board_fen_position])

    best_move = None
    best_score = -float('inf')
    alpha = -float('inf')
    beta = float('inf')

    for move in order_moves(board):
        board.push(move)
        score = -negamax(board, depth - 1, -beta, -alpha)
        board.pop()

        if score > best_score:
            best_score = score
            best_move = move
        if score > alpha:
            alpha = score

    return best_move if best_move else list(board.legal_moves)[0]

def uci_loop():
    """Main UCI Protocol Loop."""
    board = chess.Board()

    while True:
        line = sys.stdin.readline()
        if not line:
            break

        line = line.strip()
        if line == "uci":
            print("id name Zugzwang v0.1")
            print("uciok")
            sys.stdout.flush()

        elif line == "isready":
            print("readyok")
            sys.stdout.flush()

        elif line == "ucinewgame":
            board = chess.Board()

        elif line.startswith("position"):
            tokens = line.split()
            if "startpos" in tokens:
                board = chess.Board()
                if "moves" in tokens:
                    move_idx = tokens.index("moves") + 1
                    for move_str in tokens[move_idx:]:
                        board.push_uci(move_str)
            elif "fen" in tokens:
                fen_idx = tokens.index("fen")
                fen_parts = []
                for token in tokens[fen_idx + 1:]:
                    if token == "moves":
                        break
                    fen_parts.append(token)
                board = chess.Board(" ".join(fen_parts))
                if "moves" in tokens:
                    move_idx = tokens.index("moves") + 1
                    for move_str in tokens[move_idx:]:
                        board.push_uci(move_str)

                elif line.startswith("go"):
            best_move = get_best_move(board, depth=3)
            
            print(f"info depth 3 score cp 0 pv {best_move.uci()}")
            sys.stdout.flush()
            
            print(f"bestmove {best_move.uci()}")
            sys.stdout.flush()


        elif line == "quit":
            break

if __name__ == "__main__":
    uci_loop()
