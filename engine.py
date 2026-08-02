#!/usr/bin/env python3
import sys
import chess
import chess.polyglot
 
# --- Transposition Table -----------------------------------------------
# Keyed by Zobrist hash (includes side-to-move), storing the best score
# found for a position along with the depth it was searched to and a
# bound flag, so shallower/irrelevant entries don't get reused as if
# they were exact. Persists across the whole game (cleared on
# "ucinewgame") so later searches in the same game benefit from earlier
# ones too, not just within one iterative-deepening call.
TT_EXACT = 0       # score is the true value of the position
TT_LOWERBOUND = 1  # real score is >= stored score (from a beta cutoff)
TT_UPPERBOUND = 2  # real score is <= stored score (failed to raise alpha)
 
transposition_table = {}
 
# Crude replacement policy: once the table gets too big, wipe it rather
# than track per-entry aging. Simple, keeps memory bounded, and a full
# table this size means most probes were missing anyway.
MAX_TT_ENTRIES = 2_000_000
 
# UCI "Depth" option bounds - lets a GUI like En Croissant change search
# depth via setoption instead of it being hardcoded.
DEFAULT_MAX_DEPTH = 5
MAX_ALLOWED_DEPTH = 20
 
# Checkmate is scored as +/-99999 (see evaluate_board) regardless of how
# many moves away it actually is, since nothing here tracks mate
# distance. Reporting that directly as "score cp 99999" to a GUI is
# nonsensical, so anything at or above this magnitude gets reported as
# "score mate N" instead, with N approximated from the remaining search
# depth - it's not an exact mate count, just a much less misleading one.
MATE_SCORE_THRESHOLD = 90000
 
# Null-move pruning: "if I let my opponent move twice in a row and I'm
# still winning by a mile, my actual move here doesn't need searching
# deeply." R is how much shallower the verification search goes; only
# attempted from at least this much remaining depth so there's still
# something meaningful left after the reduction.
# INVARIANT: NULL_MOVE_MIN_DEPTH - 1 - NULL_MOVE_REDUCTION must be >= 0,
# or the reduced-depth search below could recurse with negative depth
# (negamax only special-cases depth == 0, not negative).
NULL_MOVE_MIN_DEPTH = 3
NULL_MOVE_REDUCTION = 2
 
# Base piece values in centipawns
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}
 
# Combined value of one side's starting non-pawn material (2N+2B+2R+Q).
# Used to scale the "encourage simplification when ahead" bonus.
STARTING_PIECE_MATERIAL = (
    2 * PIECE_VALUES[chess.KNIGHT]
    + 2 * PIECE_VALUES[chess.BISHOP]
    + 2 * PIECE_VALUES[chess.ROOK]
    + PIECE_VALUES[chess.QUEEN]
)
 
# Balanced passed pawn scaling (Unchanged - Index 0 = Rank 1, Index 6 = Rank 7)
PASSED_PAWN_BONUS = [0, 5, 15, 30, 60, 120, 240, 0]
 
# Structural penalties (centipawns) - Halved and rounded
DOUBLED_PAWN_PENALTY_MG = 8
DOUBLED_PAWN_PENALTY_EG = 15
 
ISOLATED_PAWN_PENALTY_MG = 10
ISOLATED_PAWN_PENALTY_EG = 20
 
# Mini Opening Book for instant responses in the opening.
OPENING_BOOK = {
    # ==================================================================
    # 1. FIRST MOVES
    # ==================================================================
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR": "e2e4",  # White: 1. e4
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR": "e7e5",  # Black vs 1. e4 -> 1... e5
    "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR": "g8f6",  # Black vs 1. d4 -> 1... Nf6
    "rnbqkbnr/pppppppp/8/8/2P5/8/PP1PPPP1/RNBQKBNR": "e7e5",  # Black vs 1. c4 -> 1... e5
    "rnbqkbnr/pppppppp/8/8/8/5N2/PPPPPPPP/RNBQKB1R": "d7d5",  # Black vs 1. Nf3 -> 1... d5

    # ==================================================================
    # 2. OPEN GAME (1. e4 e5) & ITALIAN SYSTEM
    # ==================================================================
    "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR": "g1f3",
    "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R": "b8c6",
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R": "f1c4",
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R": "f8c5",
    "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/2P2N2/PP1P1PPP/RNBQK2R": "g8f6",
    "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R": "g8f6",
    "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1": "g8f6",
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/4P3/2N2N2/PPPP1PPP/R1BQKB1R": "f1c4",
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R": "d2d3",
    "r1bqkbnr/pppp1ppp/2n5/4p3/3PP3/5N2/PPP2PPP/RNBQKB1R": "e5d4",

    # ==================================================================
    # 3. WHITE'S RESPONSES TO OTHER BLACK DEFENSES (1. e4)
    # ==================================================================
    "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR": "g1f3",
    "rnbqkbnr/pp2pppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R": "d2d4",
    "rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNBQKBNR": "d2d4",
    "rnbqkbnr/pp1ppppp/2p5/8/4P3/8/PPPP1PPP/RNBQKBNR": "d2d4",
    "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR": "e4d5",
    "rnbqkbnr/pppppp1p/6p1/8/4P3/8/PPPP1PPP/RNBQKBNR": "d2d4",
    "rnbqkb1r/pppppppp/5n2/8/4P3/8/PPPP1PPP/RNBQKBNR": "e4e5",
    "rnbqkbnr/ppp1pppp/3p4/8/4P3/8/PPPP1PPP/RNBQKBNR": "d2d4",
    "r1bqkb1r/ppp2ppp/2n5/3pp3/2B1N3/5N2/PPPP1PPP/R1BQK2R": "c4d3",

    # ==================================================================
    # 4. BLACK REPERTOIRE VS 1. d4, 1. c4, 1. Nf3
    # ==================================================================
    "rnbqkbnr/ppp1pppp/8/3p4/3P4/8/PPP1PPPP/RNBQKBNR": "c2c4",
    "rnbqkbnr/ppp1pppp/8/3p4/2PP4/8/PP2PPPP/RNBQKBNR": "e7e6",
    "rnbqkb1r/pppppppp/5n2/8/2PP4/8/PP2PPPP/RNBQKBNR": "e7e6",
    "rnbqkb1r/pppp1ppp/4pn2/8/2PP4/2N5/PP2PPPP/R1BQKBNR": "f8b4",
    "rnbqkbnr/pppp1ppp/8/4p3/2P5/2N5/PP1PPPP1/R1BQKBNR": "g8f6",
    "rnbqkbnr/ppp1pppp/8/3p4/8/5NP1/PPPPPP1P/RNBQKB1R": "g8f6",
}
 
# Piece-Square Tables (White's perspective) - All values divided by 2 & rounded
PAWN_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
    25, 25, 25, 25, 25, 25, 25, 25,
     5,  5, 10, 15, 15, 10,  5,  5,
     3,  3,  5, 13, 13,  5,  3,  3,
     0,  0,  0, 10, 10,  0,  0,  0,
     3, -3, -5,  0,  0, -5, -3,  3,
     3,  5,  5,-10,-10,  5,  5,  3,
     0,  0,  0,  0,  0,  0,  0,  0
]
 
KNIGHT_TABLE = [
   -25,-20,-15,-15,-15,-15,-20,-25,
   -20,-10,  0,  0,  0,  0,-10,-20,
   -15,  0, 10,  8,  8, 10,  0,-15,
   -15,  3,  8,  8,  8,  8,  3,-15,
   -15,  0,  8,  8,  8,  8,  0,-15,
   -15,  3, 10,  8,  8, 10,  3,-15,
   -20,-10,  0,  3,  3,  0,-10,-20,
   -25,-20,-15,-15,-15,-15,-20,-25
]
 
BISHOP_TABLE = [
   -10, -5, -5, -5, -5, -5, -5,-10,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  3,  5,  5,  3,  0, -5,
    -5,  3,  3,  5,  5,  3,  3, -5,
    -5,  0,  5,  5,  5,  5,  0, -5,
    -5,  5,  5,  5,  5,  5,  5, -5,
    -5,  3,  0,  0,  0,  0,  3, -5,
   -10, -5, -5, -5, -5, -5, -5,-10
]
 
ROOK_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
     3,  5,  5,  5,  5,  5,  5,  3,
    -3,  0,  0,  0,  0,  0,  0, -3,
    -3,  0,  0,  0,  0,  0,  0, -3,
    -3,  0,  0,  0,  0,  0,  0, -3,
    -3,  0,  0,  0,  0,  0,  0, -3,
    -3,  0,  0,  0,  0,  0,  0, -3,
     0,  0,  0,  3,  3,  0,  0,  0
]
 
QUEEN_MIDDLEGAME_TABLE = [
   -10, -5, -5, -3, -3, -5, -5,-10,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  3,  3,  3,  3,  0, -5,
    -3,  0,  3,  3,  3,  3,  0, -3,
     0,  0,  3,  3,  3,  3,  0, -3,
    -5,  3,  3,  3,  3,  3,  0, -5,
    -5, -3, -3, -3, -3, -3, -3, -5, 
   -10, -8, -8,  5,  5, -8, -8,-10  
]
 
QUEEN_ENDGAME_TABLE = [
   -10, -5, -5, -3, -3, -5, -5,-10,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  3,  3,  3,  3,  0, -5,
    -3,  0,  3,  3,  3,  3,  0, -3,
     0,  0,  3,  3,  3,  3,  0, -3,
    -5,  3,  3,  3,  3,  3,  0, -5,
    -5,  0,  3,  0,  0,  0,  0, -5,
   -10, -5, -5, -3, -3, -5, -5,-10
]
 
KING_MIDDLEGAME_TABLE = [
   -15,-20,-20,-25,-25,-20,-20,-15,
   -15,-20,-20,-25,-25,-20,-20,-15,
   -15,-20,-20,-25,-25,-20,-20,-15,
   -15,-20,-20,-25,-25,-20,-20,-15,
   -10,-15,-15,-20,-20,-15,-15,-10,
    -5,-10,-10,-10,-10,-10,-10, -5,
    10, 10,  0,  0,  0,  0, 10, 10,
    10, 15,  5,  0,  0,  5, 15, 10
]
 
KING_ENDGAME_TABLE = [
   -25,-20,-15,-10,-10,-15,-20,-25,
   -15,-10, -5,  0,  0, -5,-10,-15,
   -15, -5, 10, 15, 15, 10, -5,-15,
   -15, -5, 15, 20, 20, 15, -5,-15,
   -15, -5, 15, 20, 20, 15, -5,-15,
   -15, -5, 10, 15, 15, 10, -5,-15,
   -15,-15,  0,  0,  0,  0,-15,-15,
   -25,-15,-15,-15,-15,-15,-15,-25
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

        if color == chess.WHITE:
            score += pawn_score
        else:
            score -= pawn_score
 
    return score
 
def evaluate_king_safety(board: chess.Board, king_sq: int, color: chess.Color) -> int:
    """Evaluates Pawn Shield and file exposure for Middlegame King safety."""
    safety_score = 0
    file_idx = chess.square_file(king_sq)
    rank_idx = chess.square_rank(king_sq)
 
    # 1. Pawn Shield (Halved & Rounded: +8 for present, -10 for missing)
    shield_rank = rank_idx + 1 if color == chess.WHITE else rank_idx - 1
    if 0 <= shield_rank <= 7:
        adjacent_files = [f for f in [file_idx - 1, file_idx, file_idx + 1] if 0 <= f <= 7]
        for f in adjacent_files:
            sq = chess.square(f, shield_rank)
            piece = board.piece_at(sq)
            if piece and piece.piece_type == chess.PAWN and piece.color == color:
                safety_score += 8
            else:
                safety_score -= 10
 
    # 2. File Exposure (Halved & Rounded: -18 for open, -10 for semi-open)
    pawns_on_file = sum(
        1 for r in range(8)
        if (p := board.piece_at(chess.square(file_idx, r))) and p.piece_type == chess.PAWN
    )
    if pawns_on_file == 0:
        safety_score -= 18  # Open file
    elif not any(
        (p := board.piece_at(chess.square(file_idx, r))) and p.piece_type == chess.PAWN and p.color == color
        for r in range(8)
    ):
        safety_score -= 10  # Semi-open file
 
    return safety_score
 
# Bishop pair bonus (Halved: 30 -> 15)
BISHOP_PAIR_BONUS = 15
 
# Rook file bonuses (Halved: 20 -> 10, 10 -> 5)
ROOK_OPEN_FILE_BONUS = 10
ROOK_SEMI_OPEN_FILE_BONUS = 5
 
def evaluate_rook_files(board: chess.Board) -> int:
    """Rewards rooks on open (no pawns) or semi-open (no own pawns) files."""
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
        table = QUEEN_ENDGAME_TABLE if in_endgame else QUEEN_MIDDLEGAME_TABLE
    elif piece_type == chess.KING:
        table = KING_ENDGAME_TABLE if in_endgame else KING_MIDDLEGAME_TABLE
    else:
        return 0
 
    sq = square if color == chess.WHITE else chess.square_mirror(square)
    return table[sq]
 
def evaluate_repetition(board: chess.Board) -> int:
    """Penalizes unnecessary repetitions when ahead."""
    if board.is_repetition(2):
        material = 0
 
        for piece in board.piece_map().values():
            value = PIECE_VALUES[piece.piece_type]
            material += value if piece.color == chess.WHITE else -value
 
        if material > 300 or material < -300:
            return -150
 
    return 0
 
def evaluate_board(board: chess.Board) -> int:
    """Complete evaluation using Material, PSTs, Pawn Structure, and King Safety."""
    if board.is_checkmate():
        return -99999
    if board.is_stalemate() or board.is_insufficient_material():
        return 0
 
    score = 0
    in_endgame = is_endgame(board)
    material_balance = 0
 
    for square, piece in board.piece_map().items():
        piece_value = PIECE_VALUES[piece.piece_type]
        is_white = piece.color == chess.WHITE
 
        # 1. Material + Piece-Square Tables
        val = piece_value + get_pst_value(piece.piece_type, square, piece.color, in_endgame)
        score += val if is_white else -val
 
        material_balance += piece_value if is_white else -piece_value
 
        # Hanging piece check - Halved penalty (divided by 6 instead of 3)
        if piece.piece_type != chess.KING:
            attackers = len(board.attackers(not piece.color, square))
            defenders = len(board.attackers(piece.color, square))
            if attackers > defenders:
                loss = piece_value // 6
                score += -loss if is_white else loss
 
    # Encourage simplification when ahead - Halved bonus scale (divided by 100 instead of 50)
    if material_balance > 300:
        black_piece_material = sum(
            PIECE_VALUES[pt] * len(board.pieces(pt, chess.BLACK))
            for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        )
        score += (STARTING_PIECE_MATERIAL - black_piece_material) // 100
 
    elif material_balance < -300:
        white_piece_material = sum(
            PIECE_VALUES[pt] * len(board.pieces(pt, chess.WHITE))
            for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        )
        score -= (STARTING_PIECE_MATERIAL - white_piece_material) // 100
 
    # 2. Pawn Structure
    score += evaluate_pawn_structure(board, in_endgame)
 
    # 3. Bishop pair
    if len(board.pieces(chess.BISHOP, chess.WHITE)) >= 2:
        score += BISHOP_PAIR_BONUS
    if len(board.pieces(chess.BISHOP, chess.BLACK)) >= 2:
        score -= BISHOP_PAIR_BONUS
 
    # 4. Rooks on open/semi-open files
    score += evaluate_rook_files(board)
 
    # 5. King Safety (Middlegame only)
    if not in_endgame:
        white_king_sq = board.king(chess.WHITE)
        black_king_sq = board.king(chess.BLACK)
 
        if white_king_sq is not None and black_king_sq is not None:
            w_safety = evaluate_king_safety(board, white_king_sq, chess.WHITE)
            b_safety = evaluate_king_safety(board, black_king_sq, chess.BLACK)
 
            score += w_safety
            score -= b_safety
 
    # FINAL PERSPECTIVE FLIP
    return score if board.turn == chess.WHITE else -score
 
 
killer_moves = {}  # depth (remaining search depth) -> [move, move]
 
def _store_killer(depth: int, move: chess.Move) -> None:
    """Records a quiet move that caused a beta cutoff at this depth."""
    if move.promotion is not None:
        return
    killers = killer_moves.setdefault(depth, [None, None])
    if move != killers[0]:
        killers[1] = killers[0]
        killers[0] = move
 
def score_move(board: chess.Board, move: chess.Move, tt_move: chess.Move = None,
                killers: list = None) -> int:
    """Assigns priority scores to moves for faster Alpha-Beta pruning."""
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
    if to_sq in [chess.E4, chess.D4, chess.E5, chess.D5]:
        return 100
    if to_sq in [chess.F3, chess.C3, chess.F6, chess.C6]:
        return 50
 
    return 0
 
def order_moves(board: chess.Board, tt_move: chess.Move = None, depth: int = None) -> list:
    """Sorts legal moves so Alpha-Beta prunes useless branches faster."""
    moves = list(board.legal_moves)
    killers = killer_moves.get(depth) if depth is not None else None
    moves.sort(key=lambda m: score_move(board, m, tt_move, killers), reverse=True)
    return moves
 
def quiescence_search(board: chess.Board, alpha: int, beta: int) -> int:
    """Searches forcing moves (captures and promotions) until stable."""
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
 
    capture_moves = [
        move for move in board.legal_moves
        if board.is_capture(move) or move.promotion
    ]
    capture_moves.sort(key=_capture_gain, reverse=True)
 
    DELTA_MARGIN = 200
 
    for move in capture_moves:
        gain = _capture_gain(move)
 
        if stand_pat + gain + DELTA_MARGIN < alpha:
            break
 
        board.push(move)
 
        score = -quiescence_search(
            board,
            -beta,
            -alpha
        )
 
        board.pop()
 
        if score >= beta:
            return beta
 
        if score > alpha:
            alpha = score
 
    return alpha
 
def _has_non_pawn_material(board: chess.Board, color: chess.Color) -> bool:
    """True if `color` has any piece besides pawns/king."""
    return bool(
        len(board.pieces(chess.KNIGHT, color))
        or len(board.pieces(chess.BISHOP, color))
        or len(board.pieces(chess.ROOK, color))
        or len(board.pieces(chess.QUEEN, color))
    )
 
def negamax(board: chess.Board, depth: int, alpha: int, beta: int, allow_null: bool = True) -> int:
    """Negamax search algorithm with Alpha-Beta pruning, move ordering, and transposition table."""
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
        score = quiescence_search(board, alpha, beta)
 
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
    """Cheap, hashable key that uniquely identifies a position for TT/PV lookups."""
    try:
        return board._transposition_key()
    except AttributeError:
        return chess.polyglot.zobrist_hash(board)
 
def _tt_store(key: int, depth: int, score: int, flag: int, move) -> None:
    """Writes an entry into the transposition table, wiping it first if it's grown past the size cap."""
    if len(transposition_table) > MAX_TT_ENTRIES:
        transposition_table.clear()
    transposition_table[key] = (depth, score, flag, move)
 
def search_at_depth(board: chess.Board, depth: int, alpha: float = -float('inf'),
                     beta: float = float('inf')):
    """Search one specific depth."""
    best_move = None
    best_score = -float('inf')
 
    key = _position_key(board)
    tt_entry = transposition_table.get(key)
    tt_move = tt_entry[3] if tt_entry is not None else None
 
    for move in order_moves(board, tt_move, depth):
        board.push(move)
        score = -negamax(
            board,
            depth - 1,
            -beta,
            -alpha
        )
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
    """Walks the transposition table to build a principal variation for UCI output."""
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
    """Iterative deepening search."""
    board_fen_position = board.fen().split(" ")[0]
 
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
 
    return best_move if best_move else list(board.legal_moves)[0]
 
def uci_loop():
    """Main UCI Protocol Loop."""
    board = chess.Board()
    options = {"Depth": DEFAULT_MAX_DEPTH}
 
    while True:
        line = sys.stdin.readline()
        if not line:
            break
 
        line = line.strip()
        if line == "uci":
            print("id name Zugzwang v0.3")
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
