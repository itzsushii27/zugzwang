import tkinter as tk
import chess
import engine  # Loads your engine.py

class ChessGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Zugzwang v0.1 Desktop GUI")
        self.board = chess.Board()
        self.selected_square = None

        # Unicode mappings
        self.PIECES = {
            'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
            'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'
        }

        # Status Label
        self.status_label = tk.Label(root, text="Your turn (White)", font=("Arial", 14, "bold"), bg="#181818", fg="white")
        self.status_label.pack(side="top", fill="x", pady=10)

        # Board Container
        self.board_frame = tk.Frame(root, bg="#404040", bd=4)
        self.board_frame.pack(padx=20, pady=10)

        # Create 8x8 Grid
        self.squares = {}
        for r in range(8):
            for c in range(8):
                sq_name = chess.square_name(chess.square(c, 7 - r))
                is_light = (r + c) % 2 == 0
                bg_color = "#f0d9b5" if is_light else "#b58863"

                btn = tk.Button(
                    self.board_frame,
                    text="",
                    font=("Arial", 36),
                    width=2,
                    height=1,
                    bg=bg_color,
                    activebackground="#729653",
                    bd=0,
                    command=lambda sq=sq_name: self.on_square_click(sq)
                )
                btn.grid(row=r, column=c)
                self.squares[sq_name] = btn

        # Reset Button
        self.reset_btn = tk.Button(root, text="Reset Game", font=("Arial", 12), command=self.reset_game)
        self.reset_btn.pack(side="bottom", pady=15)

        self.root.configure(bg="#181818")
        self.update_board()

    def update_board(self):
        for sq_code in chess.SQUARES:
            sq_name = chess.square_name(sq_code)
            piece = self.board.piece_at(sq_code)
            btn = self.squares[sq_name]

            if piece:
                symbol = self.PIECES[piece.symbol()]
                fg_color = "#ffffff" if piece.color == chess.WHITE else "#000000"
                btn.config(text=symbol, fg=fg_color)
            else:
                btn.config(text="")

    def on_square_click(self, sq_name):
        if self.selected_square is None:
            # First click: Select piece
            sq_code = chess.parse_square(sq_name)
            piece = self.board.piece_at(sq_code)
            if piece and piece.color == self.board.turn:
                self.selected_square = sq_name
                self.squares[sq_name].config(bg="#729653")
        else:
            # Second click: Attempt Move
            move_str = self.selected_square + sq_name
            
            # Reset square colors
            for r in range(8):
                for c in range(8):
                    s = chess.square_name(chess.square(c, 7 - r))
                    is_light = (r + c) % 2 == 0
                    self.squares[s].config(bg="#f0d9b5" if is_light else "#b58863")

            # Check promotion
            move = chess.Move.from_uci(move_str)
            if chess.Move.from_uci(move_str + 'q') in self.board.legal_moves:
                move = chess.Move.from_uci(move_str + 'q')

            self.selected_square = None

            if move in self.board.legal_moves:
                self.board.push(move)
                self.update_board()

                if self.board.is_game_over():
                    self.status_label.config(text="Game Over!")
                    return

                self.status_label.config(text="Zugzwang is thinking...")
                self.root.update()

                # Bot Move
                self.root.after(200, self.make_bot_move)

    def make_bot_move(self):
        if not self.board.is_game_over():
            best_move = engine.get_best_move(self.board, depth=3)
            self.board.push(best_move)
            self.update_board()

            if self.board.is_game_over():
                self.status_label.config(text="Game Over!")
            else:
                self.status_label.config(text="Your turn (White)")

    def reset_game(self):
        self.board.reset()
        self.selected_square = None
        self.status_label.config(text="Your turn (White)")
        
        for r in range(8):
            for c in range(8):
                s = chess.square_name(chess.square(c, 7 - r))
                is_light = (r + c) % 2 == 0
                self.squares[s].config(bg="#f0d9b5" if is_light else "#b58863")

        self.update_board()

if __name__ == "__main__":
    root = tk.Tk()
    app = ChessGUI(root)
    root.mainloop()
