import os, sys

# add project root to PYTHONPATH
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))          # ui/
PROJECT_ROOT = os.path.abspath(os.path.join(ROOT_DIR, ".."))   # QuantPulse root

sys.path.append(PROJECT_ROOT)

from flask import Flask, render_template, jsonify, request
from backend.state_store import stage_results

app = Flask(__name__)

@app.route("/api/stage-results")
def api_stage_results():
    strategy = request.args.get("strategy", "ORB").upper()
    return jsonify(stage_results.get(strategy, {}))



@app.route("/")
def dashboard():
    return render_template("dashboard.html")

@app.route("/strategies")
def strategies():
    return render_template("strategies.html")

@app.route("/market")
def market():
    return render_template("dashboard.html")  # optional separate page

@app.route("/orderbook")
def orderbook():
    return render_template("orderbook.html")

@app.route("/positions")
def positions():
    return render_template("positions.html")

@app.route("/trades")
def trades():
    return render_template("trades.html")

@app.route("/settings")
def settings():
    return render_template("settings.html")

@app.route("/stock-screener")
def stock_screener():
    return render_template("stock_screener.html")

if __name__ == "__main__":
    app.run(debug=True)