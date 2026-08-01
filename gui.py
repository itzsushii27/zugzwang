import sys
import chess
from flask import Flask, render_template_string, request, jsonify
import engine # Loads your engine.py

app = Flask(__name__)
board = chess.Board()

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Zugzwang v0.1 Web GUI</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            display: flex; 
            flex-direction: column; 
            align-items: center; 
            background: #181818; 
            color: white; 
            margin-top: 30px; 
        }
        #board { 
            display: grid; 
            grid-template-columns: repeat(8, 60px); 
            grid-template-rows: repeat(8, 60px); 
            border: 4px solid #404040; 
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            user-select: none;
        }
        .square { 
            width: 60px; 
            height: 60px; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            font-size: 42px; 
            cursor: pointer; 
            /* Force text rendering over Apple emoji rendering */
            font-family: "Apple Symbols", "DejaVu Sans", "Symbola", "Arial", sans-serif;
            font-variant-emoji: text;
        }
        .white-sq { background-color: #f0d9b5; }
        .black-sq { background-color: #b58863; }
        .selected { background-color: #729653 !important; }
        .status { margin-top: 20px; font-size: 1.2rem; font-weight: bold; }
        button { 
            margin-top: 15px; 
            padding: 10px 20px; 
            font-size: 1rem; 
            cursor: pointer; 
            border-radius: 6px;
            border: none;
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
        }
        button:hover { background-color: #45a049; }
    </style>
</head>
<body>
    <h2>Play vs Zugzwang v0.1</h2>
    <div id="board"></div>
    <div class="status" id="status">Your turn (White) - Click a piece to move</div>
    <button onclick="resetGame()">Reset Game</button>

    <script>
        // Unicode mapping with \\uFE0E (text style selector) appended to force non-emoji rendering
        const UNICODE_PIECES = {
            'P': '♙\\uFE0E', 'N': '♘\\uFE0E', 'B': '♗\\uFE0E', 'R': '♖\\uFE0E', 'Q': '♕\\uFE0E', 'K': '♔\\uFE0E',
            'p': '♟\\uFE0E', 'n': '♞\\uFE0E', 'b': '♝\\uFE0E', 'r': '♜\\uFE0E', 'q': '♛\\uFE0E', 'k': '♚\\uFE0E',
            '': ''
        };

        let selectedSquare = null;

        function createBoard() {
            const boardEl = document.getElementById('board');
            boardEl.innerHTML = '';
            
            for (let r = 0; r < 8; r++) {
                for (let c = 0; c < 8; c++) {
                    const sq = document.createElement('div');
                    const isLight = (r + c) % 2 === 0;
                    const sqName = String.fromCharCode(97 + c) + (8 - r);
                    
                    sq.className = `square ${isLight ? 'white-sq' : 'black-sq'}`;
                    sq.dataset.sq = sqName;
                    sq.onclick = () => handleSquareClick(sqName);
                    
                    boardEl.appendChild(sq);
                }
            }
        }

        function renderFen(fen) {
            const fenParts = fen.split(' ')[0];
            const rows = fenParts.split('/');
            
            for (let r = 0; r < 8; r++) {
                let col = 0;
                for (let char of rows[r]) {
                    if (!isNaN(char)) {
                        for (let i = 0; i < parseInt(char); i++) {
                            const sqName = String.fromCharCode(97 + col) + (8 - r);
                            const sqEl = document.querySelector(`[data-sq="${sqName}"]`);
                            sqEl.innerText = '';
                            col++;
                        }
                    } else {
                        const sqName = String.fromCharCode(97 + col) + (8 - r);
                        const sqEl = document.querySelector(`[data-sq="${sqName}"]`);
                        sqEl.innerText = UNICODE_PIECES[char] || '';
                        
                        // Distinct styling for black vs white pieces
                        const isWhitePiece = (char === char.toUpperCase());
                        sqEl.style.color = isWhitePiece ? '#ffffff' : '#222222';
                        sqEl.style.textShadow = isWhitePiece ? '0 0 3px #000000' : 'none';
                        col++;
                    }
                }
            }
        }

        function handleSquareClick(sqName) {
            if (!selectedSquare) {
                const sqEl = document.querySelector(`[data-sq="${sqName}"]`);
                if (sqEl.innerText !== '') {
                    selectedSquare = sqName;
                    sqEl.classList.add('selected');
                }
            } else {
                const move = selectedSquare + sqName;
                document.querySelectorAll('.square').forEach(el => el.classList.remove('selected'));
                
                fetch('/move', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: `move=${move}`
                })
                .then(res => res.json())
                .then(data => {
                    selectedSquare = null;
                    if (data.status === 'ok') {
                        renderFen(data.fen);
                        if (data.game_over) {
                            document.getElementById('status').innerText = 'Game Over!';
                            return;
                        }
                        document.getElementById('status').innerText = 'Zugzwang is thinking...';
                        
                        setTimeout(() => {
                            fetch('/bot_move', { method: 'POST' })
                            .then(res => res.json())
                            .then(botData => {
                                renderFen(botData.fen);
                                if (botData.game_over) {
                                    document.getElementById('status').innerText = 'Game Over!';
                                } else {
                                    document.getElementById('status').innerText = 'Your turn (White)';
                                }
                            });
                        }, 200);
                    }
                });
            }
        }

        function resetGame() {
            selectedSquare = null;
            document.querySelectorAll('.square').forEach(el => el.classList.remove('selected'));
            fetch('/reset', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                renderFen('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
                document.getElementById('status').innerText = 'Your turn (White)';
            });
        }

        createBoard();
        renderFen('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/move', methods=['POST'])
def make_move():
    move_uci = request.form.get('move')
    try:
        move = chess.Move.from_uci(move_uci)
        if chess.Move.from_uci(move_uci + 'q') in board.legal_moves:
            move = chess.Move.from_uci(move_uci + 'q')

        if move in board.legal_moves:
            board.push(move)
            return jsonify({'status': 'ok', 'fen': board.fen(), 'game_over': board.is_game_over()})
    except Exception:
        pass
    return jsonify({'status': 'illegal'})

@app.route('/bot_move', methods=['POST'])
def bot_move():
    if not board.is_game_over():
        best_move = engine.get_best_move(board, depth=3)
        board.push(best_move)
    return jsonify({'fen': board.fen(), 'game_over': board.is_game_over()})

@app.route('/reset', methods=['POST'])
def reset():
    board.reset()
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    print("\nStarting Web GUI...")
    print("Open your browser and go to: http://127.0.0.1:5000\n")
    app.run(port=5000)
