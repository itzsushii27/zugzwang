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

# Balanced passed pawn scaling (Index 0 = Rank 1, Index 6 = Rank 7)
PASSED_PAWN_BONUS = [0, 5, 15, 30, 60, 120, 240, 0]

# Structural penalties (centipawns)
DOUBLED_PAWN_PENALTY_MG = 15
DOUBLED_PAWN_PENALTY_EG = 30

ISOLATED_PAWN_PENALTY_MG = 20
ISOLATED_PAWN_PENALTY_EG = 40

# Pre-allocated square sets for move ordering (prevents object creation in search loop)
CENTER_SQUARES = {chess.E4, chess.D4, chess.E5, chess.D5}
DEVELOPMENT_SQUARES = {chess.F3, chess.C3, chess.F6, chess.C6}

# Mini Opening Book for instant responses in the opening.
# --- Expanded Opening Book for White & Black --------------------------
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
    # 1. e4 e5 -> 2. Nf3
    "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR": "g1f3",

    # 1. e4 e5 2. Nf3 -> 2... Nc6 (Black replaces Petrov 2... Nf6)
    "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R": "b8c6",

    # 1. e4 e5 2. Nf3 Nc6 -> 3. Bc4 (White plays Italian Game)
    "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R": "f1c4",

    # 1. e4 e5 2. Nf3 Nc6 3. Bc4 -> 3... Bc5 (Black Giuoco Piano)
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R": "f8c5",

    # Black responses to White's 4th move in Italian Game:
    "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/2P2N2/PP1P1PPP/RNBQK2R": "g8f6",  # vs 4. c3 -> 4... Nf6
    "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R": "g8f6",  # vs 4. d3 -> 4... Nf6
    "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1": "g8f6",  # vs 4. O-O -> 4... Nf6

    # 1. e4 e5 2. Nf3 Nc6 3. Nc3 Nf6 -> 4. Bc4 (White plays Italian Four Knights)
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/4P3/2N2N2/PPPP1PPP/R1BQKB1R": "f1c4",

    # 1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 -> 4. d3 (White against Two Knights Defense)
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R": "d2d3",

    # --- Other Open Games (Scotch, Four Knights) ---
    "r1bqkbnr/pppp1ppp/2n5/4p3/3PP3/5N2/PPP2PPP/RNBQKB1R": "e5d4",  # Black vs Scotch 3. d4 -> 3... exd4

    # ==================================================================
    # 3. WHITE'S RESPONSES TO OTHER BLACK DEFENSES (1. e4)
    # ==================================================================
    "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR": "g1f3",  # vs Sicilian 1... c5
    "rnbqkbnr/pp2pppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R": "d2d4",  # vs Sicilian ...d6 -> 3. d4
    "rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNBQKBNR": "d2d4",  # vs French 1... e6
    "rnbqkbnr/pp1ppppp/2p5/8/4P3/8/PPPP1PPP/RNBQKBNR": "d2d4",  # vs Caro-Kann 1... c6
    "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR": "e4d5",  # vs Scandinavian 1... d5
    "rnbqkbnr/pppppp1p/6p1/8/4P3/8/PPPP1PPP/RNBQKBNR": "d2d4",  # vs Modern 1... g6
    "rnbqkb1r/pppppppp/5n2/8/4P3/8/PPPP1PPP/RNBQKBNR": "e4e5",  # vs Alekhine 1... Nf6
    "rnbqkbnr/ppp1pppp/3p4/8/4P3/8/PPPP1PPP/RNBQKBNR": "d2d4",  # vs Pirc 1... d6

    # ==================================================================
    # 4. BLACK REPERTOIRE VS 1. d4, 1. c4, 1. Nf3
    # ==================================================================
    # vs 1. d4
    "rnbqkbnr/ppp1pppp/8/3p4/3P4/8/PPP1PPPP/RNBQKBNR": "c2c4",  # White 2. c4
    "rnbqkbnr/ppp1pppp/8/3p4/2PP4/8/PP2PPPP/RNBQKBNR": "e7e6",  # Black 2... e6 (QGD)
    "rnbqkb1r/pppppppp/5n2/8/2PP4/8/PP2PPPP/RNBQKBNR": "e7e6",  # 1. d4 Nf6 2. c4 e6
    "rnbqkb1r/pppp1ppp/4pn2/8/2PP4/2N5/PP2PPPP/R1BQKBNR": "f8b4",  # 3. Nc3 -> 3... Bb4 (Nimzo-Indian)

    # vs 1. c4 (English)
    "rnbqkbnr/pppp1ppp/8/4p3/2P5/2N5/PP1PPPP1/R1BQKBNR": "g8f6",

    # vs 1. Nf3 (Reti)
    "rnbqkbnr/ppp1pppp/8/3p4/8/5NP1/PPPPPP1P/RNBQKB1R": "g8f6",
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

def is_passed_pawn(board: chess.Board, square: int, color: chess.Color) -> bool:
    """Checks if a pawn is passed using fast bitmask operations."""
    file_idx = chess.square_file(square)
    rank_idx = chess.square_rank(square)
    enemy_pawns = board.pieces(chess.PAWN, not color)

    # Calculate bitmask for ranks in front of the pawn
    if color == chess.WHITE:
        forward_mask = 0xFFFFFFFFFFFFFFFF << ((rank_idx + 1) * 8)
    else:
        forward_mask = (1 << (rank_idx * 8)) - 1

    # File and adjacent files mask
    file_mask = chess.BB_FILES[file_idx]
    if file_idx > 0:
        file_mask |= chess.BB_FILES[file_idx - 1]
    if file_idx < 7:
        file_mask |= chess.BB_FILES[file_idx + 1]

    return not bool(enemy_pawns & forward_mask & file_mask)

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

            # Fast bitboard check for doubled pawns on same file
            if len(pawns & chess.BB_FILES[file_idx]) > 1:
                pawn_score -= doubled_penalty

            # Fast bitboard check for isolated pawns
            adj_files = 0
            if file_idx > 0:
                adj_files |= chess.BB_FILES[file_idx - 1]
            if file_idx < 7:
                adj_files |= chess.BB_FILES[file_idx + 1]

            if not (pawns & adj_files):
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

    # 1. Pawn Shield
    shield_rank = rank_idx + 1 if color == chess.WHITE else rank_idx - 1
    if 0 <= shield_rank <= 7:
        f_min = max(0, file_idx - 1)
        f_max = min(7, file_idx + 1)
        own_pawns = board.pieces(chess.PAWN, color)
        for f in range(f_min, f_max + 1):
            sq = chess.square(f, shield_rank)
            if sq in own_pawns:
                safety_score += 15
            else:
                safety_score -= 20

    # 2. File Exposure (optimized with bitmasks instead of 8 loop probes)
    file_mask = chess.BB_FILES[file_idx]
    all_pawns = board.pieces(chess.PAWN, chess.WHITE) | board.pieces(chess.PAWN, chess.BLACK)

    if not (all_pawns & file_mask):
        safety_score -= 35  # Open file
    elif not (board.pieces(chess.PAWN, color) & file_mask):
        safety_score -= 20  # Semi-open file

    return safety_score

BISHOP_PAIR_BONUS = 30
ROOK_OPEN_FILE_BONUS = 20
ROOK_SEMI_OPEN_FILE_BONUS = 10

def evaluate_rook_files(board: chess.Board) -> int:
    """Rewards rooks on open (no pawns) or semi-open (no own pawns) files."""
    score = 0
    all_pawns = board.pieces(chess.PAWN, chess.WHITE) | board.pieces(chess.PAWN, chess.BLACK)

    for color in (chess.WHITE, chess.BLACK):
        rooks = board.pieces(chess.ROOK, color)
        own_pawns = board.pieces(chess.PAWN, color)

        for rook_sq in rooks:
            f_mask = chess.BB_FILES[chess.square_file(rook_sq)]

            if not (all_pawns & f_mask):
                bonus = ROOK_OPEN_FILE_BONUS
            elif not (own_pawns & f_mask):
                bonus = ROOK_SEMI_OPEN_FILE_BONUS
            else:
                bonus = 0

            score += bonus if color == chess.WHITE else -bonus

    return score

def get_pst_value(piece_type: int, square: int, color: chess.Color, in_endgame: bool) -> int:
    """Fetches positional bonus/penalty for a piece on a given square."""
    table_mg, table_eg = PST_MAP.get(piece_type, (None, None))
    if not table_mg:
        return 0

    table = table_eg if in_endgame else table_mg
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
    """Complete evaluation using Material, PSTs, Mobility, Pawn Structure, and King Safety."""
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

        val = piece_value + get_pst_value(piece.piece_type, square, piece.color, in_endgame)
        score += val if is_white else -val

        material_balance += piece_value if is_white else -piece_value

        if piece.piece_type != chess.KING:
            attackers = len(board.attackers(not piece.color, square))
            defenders = len(board.attackers(piece.color, square))
            if attackers > defenders:
                loss = piece_value // 3
                score += -loss if is_white else loss

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

killer_moves = {}

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
    if to_sq in CENTER_SQUARES:
        return 100
    if to_sq in DEVELOPMENT_SQUARES:
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
    """Negamax search algorithm with Alpha-Beta pruning, move ordering,
    and a transposition table."""
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
    """Writes an entry into the transposition table, wiping it first if
    it's grown past the size cap."""
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
    """Walks transposition table best moves forward to build PV string."""
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

    # Check opening book dictionary first
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
