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
        self.status_label = tk.Label(root, text="Your turn (White)", font=("Arial", 16, "bold"), bg="#1e1e1e", fg="#ffffff")
        self.status_label.pack(side="top", fill="x", pady=15)

        # Board Container
        self.board_frame = tk.Frame(root, bg="#2b2b2b", bd=6)
        self.board_frame.pack(padx=20, pady=10)

        # Create 8x8 Grid using Canvas for true background colors
        self.squares = {}
        for r in range(8):
            for c in range(8):
                sq_name = chess.square_name(chess.square(c, 7 - r))
                is_light = (r + c) % 2 == 0
                bg_color = "#eeeed2" if is_light else "#769656" # Clean green/cream Lichess style

                canvas = tk.Canvas(
                    self.board_frame,
                    width=60,
                    height=60,
                    bg=bg_color,
                    highlightthickness=0
                )
                canvas.grid(row=r, column=c)
                canvas.bind("<Button-1>", lambda event, sq=sq_name: self.on_square_click(sq))
                
                self.squares[sq_name] = {
                    "canvas": canvas,
                    "default_bg": bg_color
                }

        # Reset Button
        self.reset_btn = tk.Button(
            root, 
            text="Reset Game", 
            font=("Arial", 12, "bold"), 
            bg="#4CAF50", 
            fg="black", 
            padx=10, 
            pady=5, 
            command=self.reset_game
        )
        self.reset_btn.pack(side="bottom", pady=15)

        self.root.configure(bg="#1e1e1e")
        self.update_board()

    def update_board(self):
        for sq_code in chess.SQUARES:
            sq_name = chess.square_name(sq_code)
            piece = self.board.piece_at(sq_code)
            canvas = self.squares[sq_name]["canvas"]

            # Clear previous piece
            canvas.delete("all")

            if piece:
                symbol = self.PIECES[piece.symbol()]
                # High contrast styling: Pure white with shadow for White, Dark Charcoal for Black
                if piece.color == chess.WHITE:
                    canvas.create_text(31, 31, text=symbol, font=("Arial", 42), fill="#000000") # Shadow
                    canvas.create_text(30, 30, text=symbol, font=("Arial", 42), fill="#ffffff") # White piece
                else:
                    canvas.create_text(30, 30, text=symbol, font=("Arial", 42), fill="#111111") # Black piece

    def on_square_click(self, sq_name):
        if self.selected_square is None:
            # First click: Select piece
            sq_code = chess.parse_square(sq_name)
            piece = self.board.piece_at(sq_code)
            if piece and piece.color == self.board.turn:
                self.selected_square = sq_name
                self.squares[sq_name]["canvas"].config(bg="#baca44") # Highlight color
        else:
            # Second click: Attempt Move
            move_str = self.selected_square + sq_name
            
            # Reset all square colors
            for s in self.squares:
                self.squares[s]["canvas"].config(bg=self.squares[s]["default_bg"])

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
        
        for s in self.squares:
            self.squares[s]["canvas"].config(bg=self.squares[s]["default_bg"])

        self.update_board()

if __name__ == "__main__":
    root = tk.Tk()
    app = ChessGUI(root)
    root.mainloop()
