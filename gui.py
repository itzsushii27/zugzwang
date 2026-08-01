import sys
from flask import Flask, render_template_string, request, jsonify
import chess
import engine # Loads your engine.py

app = Flask(__name__)
board = chess.Board()

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Zugzwang v0.1 Web GUI</title>
    <link rel="stylesheet" href="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.css">
    <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
    <script src="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.js"></script>
    <style>
        body { font-family: sans-serif; display: flex; flex-direction: column; align-items: center; background: #181818; color: white; margin-top: 30px; }
        #board { width: 400px; }
        .status { margin-top: 20px; font-size: 1.2rem; }
        button { margin-top: 15px; padding: 10px 20px; font-size: 1rem; cursor: pointer; }
    </style>
</head>
<body>
    <h2>Play vs Zugzwang v0.1</h2>
    <div id="board"></div>
    <div class="status" id="status">Your turn (White)</div>
    <button onclick="resetGame()">Reset Game</button>

    <script>
        var board = null;

        function onDrop (source, target) {
            var move = source + target;
            
            $.post("/move", {move: move}, function(data) {
                if (data.status === "illegal") {
                    return 'snapback';
                }
                
                board.position(data.fen);
                
                if (data.game_over) {
                    $('#status').text("Game Over!");
                    return;
                }

                $('#status').text("Zugzwang is thinking...");

                // Fetch Bot Move
                setTimeout(function() {
                    $.post("/bot_move", function(botData) {
                        board.position(botData.fen);
                        if (botData.game_over) {
                            $('#status').text("Game Over!");
                        } else {
                            $('#status').text("Your turn (White)");
                        }
                    });
                }, 250);
            });
        }

        board = Chessboard('board', {
            draggable: true,
            dropOffBoard: 'snapback',
            position: 'start',
            onDrop: onDrop
        });

        function resetGame() {
            $.post("/reset", function(data) {
                board.position('start');
                $('#status').text("Your turn (White)");
            });
        }
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
        # Check for promotions automatically if pawn reaches last rank
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
    print("\nStarting local Web GUI...")
    print("Open your browser and go to: http://127.0.0.1:5000\n")
    app.run(port=5000)
