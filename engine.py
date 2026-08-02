#!/usr/bin/env python3
import sys
import chess
import chess.polyglot

# --- Transposition Table -----------------------------------------------
TT_EXACT = 0       # score is the true value of the position
TT_LOWERBOUND = 1  # real score is >= stored score (from a beta cutoff)
TT_UPPERBOUND = 2  # real score is <= stored score (failed to raise alpha)

transposition_table = {}
MAX_TT_ENTRIES = 2_000_000

DEFAULT_MAX_DEPTH = 5
MAX_ALLOWED_DEPTH = 20
MATE_SCORE_THRESHOLD = 90000

NULL_MOVE_MIN_DEPTH = 3
NULL_MOVE_REDUCTION = 2

# Max depth for quiescence search to prevent runaway search trees
MAX_QSEARCH_DEPTH = 8

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

# Balanced passed pawn scaling (Index 0 = Rank 1, Index 6 = Rank 7)
PASSED_PAWN_BONUS = [0, 5, 15, 30, 60, 120, 240, 0]

DOUBLED_PAWN_PENALTY_MG = 15
DOUBLED_PAWN_PENALTY_EG = 30

ISOLATED_PAWN_PENALTY_MG = 20
ISOLATED_PAWN_PENALTY_EG = 40

BISHOP_PAIR_BONUS = 30
ROOK_OPEN_FILE_BONUS = 20
ROOK_SEMI_OPEN_FILE_BONUS = 10

# --- Expanded Opening Book for White & Black --------------------------
OPENING_BOOK = {
    # Starting Position
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR": "e2e4",  # Default 1. e4

    # 1. e4 Openings
    "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR": "g1f3",  # 1... e5 -> 2. Nf3
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R": "f1c4",  # Italian
    "r1bqkb1r/pppp1ppp/2n2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R": "d2d3",  # Giuoco Pianissimo
    "r1bqkbnr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R": "c2c3",  # Italian Mainline
    "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/2P2N2/PPPP1PPP/RNBQK2R": "d2d4",
    "rnbqkb1r/pppp1ppp/5n2/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R": "f3e5",  # Petrov Defense

    # Sicilian Defense
    "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR": "g1f3",  # 2. Nf3
    "rnbqkbnr/pp2pppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R": "d2d4",  # 2... d6 -> 3. d4
    "rnbqkbnr/pp2pppp/3p4/8/3PP3/5N2/PPP2PPP/RNBQKB1R": "c5d4",
    "rnbqkbnr/pp2pppp/3p4/8/3nP3/8/PPP2PPP/RNBQKB1R": "f3d4",
    "rnbqkb1r/pp2pppp/3p1n2/8/3NP3/8/PPP2PPP/RNBQKB1R": "b1c3",
    "rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R": "e1g1",  # Najdorf
    "r1bqkbnr/pp1ppppp/2n5/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R": "d2d4",  # Accelerated Dragon

    # French Defense
    "rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNBQKBNR": "d2d4",  # 2. d4
    "rnbqkbnr/ppp2ppp/4p3/3p4/3PP3/8/PPP2PPP/RNBQKBNR": "b1c3",  # 3. Nc3
    "rnbqkb1r/ppp2ppp/4pn2/3p4/3PP3/2N5/PPP2PPP/R1BQKBNR": "e4e5",  # 4. e5

    # Caro-Kann Defense
    "rnbqkbnr/pp1ppppp/2p5/8/4P3/8/PPPP1PPP/RNBQKBNR": "d2d4",  # 2. d4
    "rnbqkbnr/pp2pppp/2p5/3p4/3PP3/8/PPP2PPP/RNBQKBNR": "b1c3",  # 3. Nc3
    "rnbqkbnr/pp2pppp/2p5/8/3PP3/2N5/PPP2PPP/R1BQKBNR": "c3e4",  # 4. Nxe4
    "rn1qkbnr/pp2pppp/2p5/5b2/3PN3/8/PPP2PPP/R1BQKBNR": "e4g3",  # 5. Ng3

    # Pirc & Modern
    "rnbqkbnr/ppp1pppp/3p4/8/4P3/8/PPPP1PPP/RNBQKBNR": "d2d4",
    "rnbqkb1r/ppp1pppp/3p1n2/8/3PP3/8/PPP2PPP/RNBQKBNR": "b1c3",
    "rnbqkb1r/ppp1pp1p/3p1np1/8/3PP3/2N5/PPP2PPP/R1BQKBNR": "f2f4",  # Austrian Attack
    "rnbqkbnr/pppppp1p/6p1/8/4P3/8/PPPP1PPP/RNBQKBNR": "d2d4",

    # Scandinavian Defense
    "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR": "e4d5",
    "rnbqkbnr/ppp1pppp/8/3P4/8/8/PPPP1PPP/RNBQKBNR": "d1d5",
    "rnb1kbnr/ppp1pppp/8/3q4/8/8/PPPP1PPP/RNBQKBNR": "b1c3",

    # 1. d4 Openings
    "rnbqkbnr/ppp1pppp/8/3p4/3P4/8/PPP1PPPP/RNBQKBNR": "c2c4",  # Queen's Gambit
    "rnbqkbnr/ppp2ppp/4p3/3p4/2PP4/8/PP2PPPP/RNBQKBNR": "b1c3",
    "rnbqkb1r/ppp2ppp/4pn2/3p4/2PP4/2N5/PP2PPPP/R1BQKBNR": "c4d5",
    "rnbqkb1r/pppppppp/5n2/8/3P4/8/PPP1PPPP/RNBQKBNR": "c2c4",  # Indian Systems
    "rnbqkb1r/pppppp1p/5np1/8/2PP4/8/PP2PPPP/RNBQKBNR": "b1c3",
}

# --- Piece Square Tables ---
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

PST_MAP = {
    chess.PAWN: (PAWN_TABLE, PAWN_TABLE),
    chess.KNIGHT: (KNIGHT_TABLE, KNIGHT_TABLE),
    chess.BISHOP: (BISHOP_TABLE, BISHOP_TABLE),
    chess.ROOK: (ROOK_TABLE, ROOK_TABLE),
    chess.QUEEN: (QUEEN_MIDDLEGAME_TABLE, QUEEN_ENDGAME_TABLE),
    chess.KING: (KING_MIDDLEGAME_TABLE, KING_ENDGAME_TABLE),
}

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

def evaluate_pawn_structure(board: chess.Board, in_endgame: bool) -> int:
    """Evaluates passed, doubled, and isolated pawns safely and quickly."""
    score = 0
    doubled_penalty = DOUBLED_PAWN_PENALTY_EG if in_endgame else DOUBLED_PAWN_PENALTY_MG
    isolated_penalty = ISOLATED_PAWN_PENALTY_EG if in_endgame else ISOLATED_PAWN_PENALTY_MG

    w_pawns = board.pieces(chess.PAWN, chess.WHITE)
    b_pawns = board.pieces(chess.PAWN, chess.BLACK)

    for color, pawns, enemy_pawns in ((chess.WHITE, w_pawns, b_pawns), (chess.BLACK, b_pawns, w_pawns)):
        pawn_score = 0
        is_white = color == chess.WHITE

        for sq in pawns:
            file_idx = chess.square_file(sq)
            rank_idx = chess.square_rank(sq)
            relative_rank = rank_idx if is_white else 7 - rank_idx

            # Passed Pawn Mask Check
            if is_white:
                forward_mask = 0xFFFFFFFFFFFFFFFF << ((rank_idx + 1) * 8)
            else:
                forward_mask = (1 << (rank_idx * 8)) - 1

            file_mask = chess.BB_FILES[file_idx]
            if file_idx > 0:
                file_mask |= chess.BB_FILES[file_idx - 1]
            if file_idx < 7:
                file_mask |= chess.BB_FILES[file_idx + 1]

            passed_mask = forward_mask & file_mask
            if not (enemy_pawns & passed_mask):
                pawn_score += PASSED_PAWN_BONUS[relative_rank]

            # Doubled Pawn Check
            if len(pawns & chess.BB_FILES[file_idx]) > 1:
                pawn_score -= doubled_penalty

            # Isolated Pawn Check
            adj_files = 0
            if file_idx > 0:
                adj_files |= chess.BB_FILES[file_idx - 1]
            if file_idx < 7:
                adj_files |= chess.BB_FILES[file_idx + 1]

            if not (pawns & adj_files):
                pawn_score -= isolated_penalty

        score += pawn_score if is_white else -pawn_score

    return score

def evaluate_king_safety(board: chess.Board, king_sq: int, color: chess.Color) -> int:
    """Evaluates Pawn Shield and file exposure."""
    safety_score = 0
    file_idx = chess.square_file(king_sq)
    rank_idx = chess.square_rank(king_sq)
    shield_rank = rank_idx + 1 if color == chess.WHITE else rank_idx - 1

    own_pawns = board.pieces(chess.PAWN, color)

    # 1. Pawn Shield
    if 0 <= shield_rank <= 7:
        f_min = max(0, file_idx - 1)
        f_max = min(7, file_idx + 1)
        for f in range(f_min, f_max + 1):
            sq = chess.square(f, shield_rank)
            if sq in own_pawns:
                safety_score += 15
            else:
                safety_score -= 20

    # 2. File Exposure
    file_mask = chess.BB_FILES[file_idx]
    all_pawns = board.pieces(chess.PAWN, chess.WHITE) | board.pieces(chess.PAWN, chess.BLACK)

    if not (all_pawns & file_mask):
        safety_score -= 35  # Open file
    elif not (own_pawns & file_mask):
        safety_score -= 20  # Semi-open file

    return safety_score

def evaluate_rook_files(board: chess.Board) -> int:
    """Rewards rooks on open or semi-open files."""
    score = 0
    all_pawns = board.pieces(chess.PAWN, chess.WHITE) | board.pieces(chess.PAWN, chess.BLACK)

    for color in (chess.WHITE, chess.BLACK):
        rooks = board.pieces(chess.ROOK, color)
        own_pawns = board.pieces(chess.PAWN, color)
        is_white = color == chess.WHITE

        for rook_sq in rooks:
            f_mask = chess.BB_FILES[chess.square_file(rook_sq)]

            if not (all_pawns & f_mask):
                bonus = ROOK_OPEN_FILE_BONUS
            elif not (own_pawns & f_mask):
                bonus = ROOK_SEMI_OPEN_FILE_BONUS
            else:
                bonus = 0

            score += bonus if is_white else -bonus

    return score

def evaluate_board(board: chess.Board) -> int:
    """Complete evaluation using single-pass iteration."""
    if board.is_checkmate():
        return -99999
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    score = 0
    in_endgame = is_endgame(board)
    material_balance = 0

    for color in (chess.WHITE, chess.BLACK):
        is_white = color == chess.WHITE
        multiplier = 1 if is_white else -1

        for piece_type in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING):
            piece_val = PIECE_VALUES[piece_type]
            table_mg, table_eg = PST_MAP[piece_type]
            table = table_eg if in_endgame else table_mg

            squares = board.pieces(piece_type, color)

            for sq in squares:
                pst_sq = sq if is_white else chess.square_mirror(sq)
                val = piece_val + table[pst_sq]
                score += val * multiplier

                if piece_type != chess.PAWN and piece_type != chess.KING:
                    material_balance += piece_val * multiplier

                # Hanging piece check
                if piece_type != chess.KING:
                    attackers = len(board.attackers(not color, sq))
                    defenders = len(board.attackers(color, sq))
                    if attackers > defenders:
                        loss = piece_val // 3
                        score -= loss if is_white else -loss

    # Simplification Bonus
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

    # Pawn structure & Rook files
    score += evaluate_pawn_structure(board, in_endgame)
    score += evaluate_rook_files(board)

    # Bishop Pair
    if len(board.pieces(chess.BISHOP, chess.WHITE)) >= 2:
        score += BISHOP_PAIR_BONUS
    if len(board.pieces(chess.BISHOP, chess.BLACK)) >= 2:
        score -= BISHOP_PAIR_BONUS

    # King Safety
    if not in_endgame:
        w_king = board.king(chess.WHITE)
        b_king = board.king(chess.BLACK)
        if w_king is not None and b_king is not None:
            score += evaluate_king_safety(board, w_king, chess.WHITE)
            score -= evaluate_king_safety(board, b_king, chess.BLACK)

    return score if board.turn == chess.WHITE else -score

killer_moves = {}

def _store_killer(depth: int, move: chess.Move) -> None:
    if move.promotion is not None:
        return
    killers = killer_moves.setdefault(depth, [None, None])
    if move != killers[0]:
        killers[1] = killers[0]
        killers[0] = move

def score_move(board: chess.Board, move: chess.Move, tt_move: chess.Move = None, killers: list = None) -> int:
    if tt_move is not None and move == tt_move:
        return 1_000_000

    if board.is_capture(move):
        victim = board.piece_at(move.to_square)
        attacker = board.piece_at(move.from_square)
        victim_val = PIECE_VALUES[victim.piece_type] if victim else 100
        attacker_val = PIECE_VALUES[attacker.piece_type] if attacker else 100
        bonus = victim_val - attacker_val
        if victim_val >= 300:
            bonus += 150
        return 1000 + bonus

    if move.promotion:
        return 900

    if killers:
        if move == killers[0]:
            return 600
        if move == killers[1]:
            return 550

    to_sq = move.to_square
    if to_sq in (chess.E4, chess.D4, chess.E5, chess.D5):
        return 100
    if to_sq in (chess.F3, chess.C3, chess.F6, chess.C6):
        return 50

    return 0

def order_moves(board: chess.Board, tt_move: chess.Move = None, depth: int = None) -> list:
    moves = list(board.legal_moves)
    killers = killer_moves.get(depth) if depth is not None else None
    moves.sort(key=lambda m: score_move(board, m, tt_move, killers), reverse=True)
    return moves

def quiescence_search(board: chess.Board, alpha: int, beta: int, qdepth: int = 0) -> int:
    """Searches captures/promotions with depth safety cap."""
    if qdepth >= MAX_QSEARCH_DEPTH:
        return evaluate_board(board)

    stand_pat = evaluate_board(board)

    if stand_pat >= beta:
        return beta
    if stand_pat > alpha:
        alpha = stand_pat

    def _capture_gain(move: chess.Move) -> int:
        if move.promotion:
            return PIECE_VALUES[move.promotion]
        victim = board.piece_at(move.to_square)
        return PIECE_VALUES[victim.piece_type] if victim else 100

    capture_moves = [m for m in board.legal_moves if board.is_capture(m) or m.promotion]
    capture_moves.sort(key=_capture_gain, reverse=True)

    DELTA_MARGIN = 200

    for move in capture_moves:
        gain = _capture_gain(move)

        if stand_pat + gain + DELTA_MARGIN < alpha:
            break

        board.push(move)
        score = -quiescence_search(board, -beta, -alpha, qdepth + 1)
        board.pop()

        if score >= beta:
            return beta
        if score > alpha:
            alpha = score

    return alpha

def _has_non_pawn_material(board: chess.Board, color: chess.Color) -> bool:
    return bool(
        len(board.pieces(chess.KNIGHT, color))
        or len(board.pieces(chess.BISHOP, color))
        or len(board.pieces(chess.ROOK, color))
        or len(board.pieces(chess.QUEEN, color))
    )

def negamax(board: chess.Board, depth: int, alpha: int, beta: int, allow_null: bool = True) -> int:
    if board.is_repetition(2):
        eval_score = evaluate_board(board)
        if eval_score > 150:
            return -200
        if eval_score < -150:
            return 200
        return 0

    if board.is_game_over():
        return evaluate_board(board)

    original_alpha = alpha
    original_beta = beta

    key = _position_key(board)
    tt_entry = transposition_table.get(key)
    tt_move = None

    if tt_entry is not None:
        tt_depth, tt_score, tt_flag, tt_move = tt_entry
        if tt_depth >= depth:
            if tt_flag == TT_EXACT:
                return tt_score
            elif tt_flag == TT_LOWERBOUND and tt_score > alpha:
                alpha = tt_score
            elif tt_flag == TT_UPPERBOUND and tt_score < beta:
                beta = tt_score

            if alpha >= beta:
                return tt_score

    if depth == 0:
        score = quiescence_search(board, alpha, beta, 0)

        if score <= original_alpha:
            flag = TT_UPPERBOUND
        elif score >= original_beta:
            flag = TT_LOWERBOUND
        else:
            flag = TT_EXACT

        _tt_store(key, depth, score, flag, None)
        return score

    if (
        allow_null
        and depth >= NULL_MOVE_MIN_DEPTH
        and not board.is_check()
        and abs(beta) < MATE_SCORE_THRESHOLD
        and _has_non_pawn_material(board, board.turn)
    ):
        board.push(chess.Move.null())
        null_score = -negamax(
            board,
            depth - 1 - NULL_MOVE_REDUCTION,
            -beta,
            -beta + 1,
            allow_null=False,
        )
        board.pop()

        if null_score >= beta:
            return beta

    max_score = -float('inf')
    best_move_here = None

    for move in order_moves(board, tt_move, depth):
        is_capture = board.is_capture(move)
        board.push(move)
        score = -negamax(board, depth - 1, -beta, -alpha)
        board.pop()

        if score > max_score:
            max_score = score
            best_move_here = move
        if score > alpha:
            alpha = score
        if alpha >= beta:
            if not is_capture:
                _store_killer(depth, move)
            break

    if max_score <= original_alpha:
        flag = TT_UPPERBOUND
    elif max_score >= original_beta:
        flag = TT_LOWERBOUND
    else:
        flag = TT_EXACT

    _tt_store(key, depth, max_score, flag, best_move_here)

    return max_score

def _position_key(board: chess.Board):
    try:
        return board._transposition_key()
    except AttributeError:
        return chess.polyglot.zobrist_hash(board)

def _tt_store(key: int, depth: int, score: int, flag: int, move) -> None:
    if len(transposition_table) > MAX_TT_ENTRIES:
        transposition_table.clear()
    transposition_table[key] = (depth, score, flag, move)

def search_at_depth(board: chess.Board, depth: int, alpha: float = -float('inf'), beta: float = float('inf')):
    best_move = None
    best_score = -float('inf')

    key = _position_key(board)
    tt_entry = transposition_table.get(key)
    tt_move = tt_entry[3] if tt_entry is not None else None

    for move in order_moves(board, tt_move, depth):
        board.push(move)
        score = -negamax(board, depth - 1, -beta, -alpha)
        board.pop()

        if score > best_score:
            best_score = score
            best_move = move

        if score > alpha:
            alpha = score

    if best_move is not None:
        _tt_store(key, depth, best_score, TT_EXACT, best_move)

    return best_move, best_score

def extract_pv(board: chess.Board, max_length: int) -> list:
    pv = []
    b = board.copy(stack=False)

    for _ in range(max_length):
        key = _position_key(b)
        entry = transposition_table.get(key)
        if entry is None or entry[3] is None:
            break

        move = entry[3]
        if move not in b.legal_moves:
            break

        pv.append(move)
        b.push(move)

    return pv

def get_best_move(board: chess.Board, max_depth: int = DEFAULT_MAX_DEPTH):
    board_fen_position = board.fen().split(" ")[0]

    # Polyglot book check if book.bin exists, fallback to OPENING_BOOK dict
    try:
        with chess.polyglot.open_reader("book.bin") as reader:
            entry = reader.find(board)
            print(f"info depth 0 score cp 0 pv {entry.move.uci()} string polyglot book move")
            sys.stdout.flush()
            return entry.move
    except (FileNotFoundError, IOError, IndexError):
        if board_fen_position in OPENING_BOOK:
            book_move = chess.Move.from_uci(OPENING_BOOK[board_fen_position])
            print(f"info depth 0 score cp 0 pv {book_move.uci()} string book move")
            sys.stdout.flush()
            return book_move

    killer_moves.clear()
    best_move = None
    prev_score = None
    ASPIRATION_WINDOW = 50

    for depth in range(1, max_depth + 1):
        if prev_score is None:
            alpha, beta = -float('inf'), float('inf')
        else:
            alpha = prev_score - ASPIRATION_WINDOW
            beta = prev_score + ASPIRATION_WINDOW

        move, score = search_at_depth(board, depth, alpha, beta)

        if score <= alpha or score >= beta:
            move, score = search_at_depth(board, depth, -float('inf'), float('inf'))

        if move:
            best_move = move

        prev_score = score if abs(score) < MATE_SCORE_THRESHOLD else None

        pv_moves = extract_pv(board, depth)
        if not pv_moves and best_move is not None:
            pv_moves = [best_move]
        pv_str = " ".join(m.uci() for m in pv_moves)

        if abs(score) >= MATE_SCORE_THRESHOLD:
            mate_in = max(1, (depth + 1) // 2)
            mate_score = mate_in if score > 0 else -mate_in
            print(f"info depth {depth} score mate {mate_score} pv {pv_str}")
        else:
            print(f"info depth {depth} score cp {int(score)} pv {pv_str}")
        sys.stdout.flush()

    if best_move is None:
        legal_moves = list(board.legal_moves)
        return legal_moves[0] if legal_moves else chess.Move.null()

    return best_move

def uci_loop():
    board = chess.Board()
    options = {"Depth": DEFAULT_MAX_DEPTH}

    while True:
        line = sys.stdin.readline()
        if not line:
            break

        line = line.strip()
        if line == "uci":
            print("id name Zugzwang v0.3-opt")
            print("id author Zugzwang contributors")
            print(f"option name Depth type spin default {DEFAULT_MAX_DEPTH} min 1 max {MAX_ALLOWED_DEPTH}")
            print("uciok")
            sys.stdout.flush()
        elif line == "isready":
            print("readyok")
            sys.stdout.flush()

        elif line == "ucinewgame":
            board = chess.Board()
            transposition_table.clear()
            killer_moves.clear()

        elif line.startswith("setoption"):
            tokens = line.split()
            if "name" in tokens:
                name_idx = tokens.index("name") + 1
                if "value" in tokens:
                    value_idx = tokens.index("value")
                    opt_name = " ".join(tokens[name_idx:value_idx])
                    opt_value = " ".join(tokens[value_idx + 1:])
                else:
                    opt_name = " ".join(tokens[name_idx:])
                    opt_value = None

                if opt_name.strip().lower() == "depth" and opt_value is not None:
                    try:
                        requested = int(opt_value)
                        options["Depth"] = max(1, min(MAX_ALLOWED_DEPTH, requested))
                    except ValueError:
                        pass

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
            best_move = get_best_move(board, max_depth=options["Depth"])
            print(f"bestmove {best_move.uci()}")
            sys.stdout.flush()

        elif line == "quit":
            break

if __name__ == "__main__":
    uci_loop()
