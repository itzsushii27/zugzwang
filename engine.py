import sys
import chess

# Piece values in centipawns
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}

def evaluate_board(board: chess.Board) -> int:
    """
    Evaluates the board relative to the side to move (Negamax perspective).
    Positive score = good for current turn, Negative = bad.
    """
    if board.is_checkmate():
        return -99999  # Current player lost
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    score = 0
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece:
            val = PIECE_VALUES[piece.piece_type]
            score += val if piece.color == board.turn else -val
    return score

def quiescence_search(board: chess.Board, alpha: int, beta: int) -> int:
    """
    Searches only capture moves until a quiet position is reached.
    Prevents blunders caused by stopping search mid-tactical trade.
    """
    stand_pat = evaluate_board(board)
    
    if stand_pat >= beta:
        return beta
    if alpha < stand_pat:
        alpha = stand_pat

    # Only look at legal captures (tactical moves)
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
    """
    Negamax search algorithm with Alpha-Beta pruning & Quiescence search.
    """
    if board.is_game_over():
        return evaluate_board(board)

    # Reached search limit -> hand off to Quiescence Search instead of raw static eval
    if depth == 0:
        return quiescence_search(board, alpha, beta)

    max_score = -float('inf')

    for move in board.legal_moves:
        board.push(move)
        # Flip perspective with negative sign and swap alpha/beta bounds
        score = -negamax(board, depth - 1, -beta, -alpha)
        board.pop()

        if score > max_score:
            max_score = score
        if score > alpha:
            alpha = score
        if alpha >= beta:
            break  # Alpha-Beta Pruning Cutoff

    return max_score

def get_best_move(board: chess.Board, depth: int = 3) -> chess.Move:
    """Finds the optimal move using the Negamax framework."""
    best_move = None
    best_score = -float('inf')
    alpha = -float('inf')
    beta = float('inf')

    for move in board.legal_moves:
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
    """UCI Communication Loop for CCRL Compatible GUIs."""
    board = chess.Board()

    while True:
        line = sys.stdin.readline()
        if not line:
            break

        line = line.strip()
        if line == "uci":
            print("Zugzwang v0.1")
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
            # Quiescence search lets us use depth 3/4 cleanly without tactical blunders
            best_move = get_best_move(board, depth=3)
            print(f"bestmove {best_move.uci()}")
            sys.stdout.flush()

        elif line == "quit":
            break

if __name__ == "__main__":
    uci_loop()
