import os, sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(ROOT_DIR, ".."))
sys.path.append(PROJECT_ROOT)

from flask import Flask, render_template, jsonify, request
from backend.state_store import stage_results
from backend.market_analysis_engine import MarketAnalysisEngine
from backend.report_generator import generate_report

# ---------------------------------------
# App Factory (Receives live_engine)
# ---------------------------------------
def create_app(live_engine):

    app = Flask(__name__)
    analysis_engine = MarketAnalysisEngine(live_engine)

    @app.route("/")
    def home():
        return render_template("live.html")
    
    @app.route("/api/live-status")
    def live_status():
        snapshot = live_engine.get_snapshot()
        return jsonify({
            "symbols": len(snapshot),
            "status": "RUNNING"
        })

    @app.route("/api/stage-results")
    def api_stage_results():
        strategy = request.args.get("strategy", "ORB").upper()
        return jsonify(stage_results.get(strategy, {}))

    @app.route("/market-analysis")
    def market_analysis_page():
        return render_template("market_analysis.html")
    
    @app.route("/api/market-analysis")
    def api_market_analysis():
        index_symbol = request.args.get("symbol", "NIFTY 50")
        data = analysis_engine.analyze(index_symbol)
        return jsonify(data)

    @app.route("/api/download-report")
    def download_report():
        index_symbol = request.args.get("symbol", "NIFTY 50")
        data = analysis_engine.analyze(index_symbol)
        filepath = generate_report(data, index_symbol)
        return jsonify({"file": filepath})

    @app.route("/stock-screener")
    def stock_screener():
        return render_template("stock_screener.html")

    @app.route("/api/screener-live")
    def screener_live():

        snapshot = live_engine.get_snapshot()
        orb_stages = stage_results.get("ORB", {})

        s1 = orb_stages.get("stage1", {}).get("stocks", [])
        s2 = orb_stages.get("stage2", {}).get("stocks", [])
        s3 = orb_stages.get("stage3", {}).get("stocks", [])

        result = []

        for symbol, data in snapshot.items():

            stage = "None"

            if symbol in s3:
                stage = "Stage 3"
            elif symbol in s2:
                stage = "Stage 2"
            elif symbol in s1:
                stage = "Stage 1"

            result.append({
                "symbol": symbol,
                "stage": stage,
                "ltp": data.get("ltp"),
                "vwap": data.get("vwap"),
                "rsi": data.get("rsi"),
                "volume_ratio": data.get("volume_ratio"),
                "atr_pct": data.get("atr_pct"),
                "orb_low": data.get("orb_low"),
                "distance_to_or_low": data.get("distance_to_or_low")
            })

        return jsonify(result)

    @app.route("/strategies")
    def strategies():
        return render_template("strategies.html")

    @app.route("/market")
    def market():
        return render_template("dashboard.html")

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

    @app.route("/live")
    def live_dashboard():
        return render_template("live.html")
    

    return app