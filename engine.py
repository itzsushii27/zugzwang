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

# Mini Opening Book for instant responses in the opening
OPENING_BOOK = {
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR": "e2e4",  # Start pos -> 1. e4
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR": "e7e5",  # 1. e4 -> 1... e5
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

        # Always accumulate in absolute White-positive terms, same as
        # material/PST/king-safety - evaluate_board does the one and only
        # side-to-move flip at the very end. Flipping on board.turn here
        # too (instead of on `color`) meant this term came out with the
        # wrong sign relative to everything else whenever it was Black's
        # turn - a passed pawn for White would score as bad for White in
        # roughly half of all evaluated positions.
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

# Standard heuristic that was missing entirely: two bishops are worth a
# little more together than the sum of their piece values would suggest
# (better coverage of both color complexes). Doesn't depend on whose
# turn it is, so - like material/PST/king safety - it's added in plain
# absolute (White-positive) terms.
BISHOP_PAIR_BONUS = 30

# Also missing: rooks get no credit at all for sitting on an open or
# semi-open file, even though the pawn-file logic to compute that already
# existed for king safety above. A rook behind no pawns (open) or only
# enemy pawns (semi-open) has much more scope.
ROOK_OPEN_FILE_BONUS = 20
ROOK_SEMI_OPEN_FILE_BONUS = 10

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

def evaluate_hanging_pieces(board: chess.Board) -> int:
    """Penalizes pieces that are attacked more times than they are defended.

    NOTE: This used to be mis-indented so it only ever ran once, on
    whichever piece happened to be last in board.piece_map().items() -
    it never actually checked most pieces on the board. That's why the
    engine would casually leave pieces hanging: this safety check was
    silently a no-op for ~63 of the 64 squares. Fixed by keeping the
    attacker/defender check inside the loop over every piece.
    """
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

def evaluate_repetition(board: chess.Board) -> int:
    """Penalizes unnecessary repetitions when ahead."""
    
    # Only care if the position has actually repeated
    if board.is_repetition(2):
        material = 0

        for piece in board.piece_map().values():
            value = PIECE_VALUES[piece.piece_type]
            material += value if piece.color == chess.WHITE else -value

        # White is ahead
        if material > 300:
            return -150

        # Black is ahead
        elif material < -300:
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

    # 0. Hanging piece safety check (was previously broken - see function docstring)
    score += evaluate_hanging_pieces(board)

    # 1. Material + Piece-Square Tables (White is positive, Black is negative)
    for square, piece in board.piece_map().items():
        val = PIECE_VALUES[piece.piece_type] + get_pst_value(
            piece.piece_type,
            square,
            piece.color,
            in_endgame
        )
        score += val if piece.color == chess.WHITE else -val

    # Encourage simplification when ahead
    material_balance = 0

    for piece in board.piece_map().values():
        value = PIECE_VALUES[piece.piece_type]
        material_balance += value if piece.color == chess.WHITE else -value

    # Encourage simplification when ahead: the standard chess principle is
    # trade PIECES, keep PAWNS - extra pawns are what actually wins a won
    # endgame, and fewer defending pieces makes the win easier to convert.
    # (The old version did the opposite: it only rewarded reducing the
    # opponent's pawn count and never looked at pieces at all.)
    if material_balance > 300:
        # White is ahead: reward trading off Black's remaining pieces
        black_piece_material = sum(
            PIECE_VALUES[pt] * len(board.pieces(pt, chess.BLACK))
            for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        )
        score += (STARTING_PIECE_MATERIAL - black_piece_material) // 50

    elif material_balance < -300:
        # Black is ahead: reward trading off White's remaining pieces
        white_piece_material = sum(
            PIECE_VALUES[pt] * len(board.pieces(pt, chess.WHITE))
            for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        )
        score -= (STARTING_PIECE_MATERIAL - white_piece_material) // 50

    # 2. Piece Mobility (disabled)
    # score += get_mobility_score(board)

    # 3. Pawn Structure
    score += evaluate_pawn_structure(board, in_endgame)

    # 3b. Bishop pair
    if len(board.pieces(chess.BISHOP, chess.WHITE)) >= 2:
        score += BISHOP_PAIR_BONUS
    if len(board.pieces(chess.BISHOP, chess.BLACK)) >= 2:
        score -= BISHOP_PAIR_BONUS

    # 3c. Rooks on open/semi-open files
    score += evaluate_rook_files(board)

    # 4. King Safety (White adds safety, Black subtracts safety)
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


def score_move(board: chess.Board, move: chess.Move, tt_move: chess.Move = None) -> int:
    """Assigns priority scores to moves for faster Alpha-Beta pruning."""
    if tt_move is not None and move == tt_move:
        # Whatever the TT says was best here last time (even from a
        # shallower search) goes first - this is what actually makes
        # iterative deepening pay for itself instead of just repeating work.
        return 1_000_000

    if board.is_capture(move):
        victim = board.piece_at(move.to_square)
        attacker = board.piece_at(move.from_square)
        victim_val = PIECE_VALUES[victim.piece_type] if victim else 100
        attacker_val = PIECE_VALUES[attacker.piece_type] if attacker else 100
        bonus = victim_val - attacker_val

        eval_now = evaluate_board(board)

        if eval_now > 300 and victim_val >= 300:
            bonus += 300

        return 1000 + bonus

    if board.gives_check(move):
        return 500

    to_sq = move.to_square
    if to_sq in [chess.E4, chess.D4, chess.E5, chess.D5]:
        return 100
    if to_sq in [chess.F3, chess.C3, chess.F6, chess.C6]:
        return 50

    return 0

def order_moves(board: chess.Board, tt_move: chess.Move = None) -> list:
    """Sorts legal moves so Alpha-Beta prunes useless branches faster."""
    moves = list(board.legal_moves)
    moves.sort(key=lambda m: score_move(board, m, tt_move), reverse=True)
    return moves

def quiescence_search(board: chess.Board, alpha: int, beta: int) -> int:
    """Searches forcing moves (captures, checks, promotions) until stable."""

    stand_pat = evaluate_board(board)

    if stand_pat >= beta:
        return beta

    if stand_pat > alpha:
        alpha = stand_pat


    for move in board.legal_moves:

        # Only search forcing moves
        if not (
            board.is_capture(move)
            or (
                board.gives_check(move)
                and (
                    board.piece_at(move.from_square) is None
                    or PIECE_VALUES[board.piece_at(move.from_square).piece_type] <= PIECE_VALUES[chess.KNIGHT]
                    or not board.is_attacked_by(not board.turn, move.to_square)
                )
            )
            or move.promotion
        ):
            continue

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

def negamax(board: chess.Board, depth: int, alpha: int, beta: int) -> int:
    """Negamax search algorithm with Alpha-Beta pruning, move ordering,
    and a transposition table."""

    # Discourage unnecessary repetitions when ahead.
    # NOTE: deliberately checked BEFORE the transposition table and never
    # cached - the position's Zobrist hash doesn't know how it was
    # reached, but whether it's a repetition depends on move history, so
    # caching this would risk reusing a repetition penalty/bonus in a
    # line that didn't actually repeat.
    if board.is_repetition(2):
        eval_score = evaluate_board(board)

        if eval_score > 150:
            return -200

        if eval_score < -150:
            return 200

        return 0

    if board.is_game_over():
        return evaluate_board(board)

    # Keep the caller's original window separately - alpha/beta below may
    # get tightened using TT bounds, but a stored entry's flag must be
    # classified against what the *caller* asked for, not the tightened
    # window, or the bound type we save becomes wrong.
    original_alpha = alpha
    original_beta = beta

    key = chess.polyglot.zobrist_hash(board)
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

    max_score = -float('inf')
    best_move_here = None

    for move in order_moves(board, tt_move):
        board.push(move)
        score = -negamax(board, depth - 1, -beta, -alpha)
        board.pop()

        if score > max_score:
            max_score = score
            best_move_here = move
        if score > alpha:
            alpha = score
        if alpha >= beta:
            break

    if max_score <= original_alpha:
        flag = TT_UPPERBOUND
    elif max_score >= original_beta:
        flag = TT_LOWERBOUND
    else:
        flag = TT_EXACT

    _tt_store(key, depth, max_score, flag, best_move_here)

    return max_score


def _tt_store(key: int, depth: int, score: int, flag: int, move) -> None:
    """Writes an entry into the transposition table, wiping it first if
    it's grown past the size cap."""
    if len(transposition_table) > MAX_TT_ENTRIES:
        transposition_table.clear()
    transposition_table[key] = (depth, score, flag, move)

def search_at_depth(board: chess.Board, depth: int):
    """Search one specific depth. Returns (best_move, best_score) - the
    score is needed so the UCI layer can report a real eval instead of a
    hardcoded placeholder.

    Uses whatever the transposition table already knows about this exact
    position (e.g. from the previous, shallower iterative-deepening pass)
    to order moves at the root, then updates the table so the *next*
    depth iteration gets the improved move ordering in turn.
    """

    best_move = None
    best_score = -float('inf')

    alpha = -float('inf')
    beta = float('inf')

    key = chess.polyglot.zobrist_hash(board)
    tt_entry = transposition_table.get(key)
    tt_move = tt_entry[3] if tt_entry is not None else None

    for move in order_moves(board, tt_move):

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
    """Walks the transposition table's stored best moves forward from the
    given position to build a principal variation for UCI 'info ... pv'
    output, so a GUI like En Croissant can show more than just the next
    move."""
    pv = []
    b = board.copy(stack=False)

    for _ in range(max_length):
        key = chess.polyglot.zobrist_hash(b)
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
    """Iterative deepening search. Prints a UCI 'info' line after each
    completed depth so a GUI can show a live, real eval instead of the
    previous hardcoded 'score cp 0'."""

    # Opening book first
    board_fen_position = board.fen().split(" ")[0]

    if board_fen_position in OPENING_BOOK:
        book_move = chess.Move.from_uci(OPENING_BOOK[board_fen_position])
        print(f"info depth 0 score cp 0 pv {book_move.uci()} string book move")
        sys.stdout.flush()
        return book_move

    best_move = None

    # Search depth 1, then 2, then 3...
    for depth in range(1, max_depth + 1):

        move, score = search_at_depth(
            board,
            depth
        )

        if move:
            best_move = move

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
