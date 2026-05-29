"""
REST API endpoints — ทุก endpoint คืน JSON

จัดกลุ่มตามฟีเจอร์ทั้ง 14 อย่าง เพื่อให้ frontend เรียกใช้ผ่าน /api/...
โค้ดบาง endpoint ห่อด้วย try/except กลางที่ตัว blueprint (ดู error handler)
"""
from flask import Blueprint, request, jsonify

from config import Config
from database import query, execute
from services import (
    stock_data, technical, fundamental, news, sentiment as sentiment_svc,
    macro, scoring, screener, portfolio, risk, backtest, institutional,
    alerts, daily_report, ai_advisory,
)

api = Blueprint("api", __name__, url_prefix="/api")


@api.errorhandler(Exception)
def handle_error(e):
    return jsonify({"ok": False, "error": str(e)}), 500


def _args():
    return request.get_json(silent=True) or request.form.to_dict() or {}


# ---------------- ราคา/ค้นหา ----------------
@api.get("/quote/<ticker>")
def quote(ticker):
    return jsonify(stock_data.get_quote(ticker))


@api.post("/quotes")
def quotes():
    tickers = _args().get("tickers", [])
    return jsonify({"quotes": stock_data.get_quotes(tickers)})


@api.get("/history/<ticker>")
def history(ticker):
    period = request.args.get("period", "1y")
    interval = request.args.get("interval", "1d")
    return jsonify(stock_data.get_history(ticker, period, interval))


@api.get("/search")
def search():
    return jsonify({"results": stock_data.search_symbols(request.args.get("q", ""))})


# ---------------- 1) Screener ----------------
@api.post("/screener")
def screen():
    a = _args()
    market = a.pop("market", "th")
    return jsonify(screener.screen(a, market=market))


# ---------------- 2) Fundamental ----------------
@api.get("/fundamental/<ticker>")
def fundamental_ep(ticker):
    return jsonify(fundamental.analyze(ticker))


@api.post("/compare")
def compare():
    return jsonify(fundamental.compare(_args().get("tickers", [])))


# ---------------- 3) Technical ----------------
@api.get("/technical/<ticker>")
def technical_ep(ticker):
    return jsonify(technical.analyze(ticker, request.args.get("period", "1y")))


# ---------------- 4) Sentiment ----------------
@api.get("/sentiment/<ticker>")
def sentiment_ep(ticker):
    return jsonify(sentiment_svc.stock_sentiment(ticker))


@api.get("/fear-greed")
def fear_greed():
    return jsonify(sentiment_svc.fear_greed(request.args.get("market", "us")))


@api.get("/news")
def news_ep():
    return jsonify(news.get_news(query=request.args.get("q", ""),
                                 ticker=request.args.get("ticker", ""),
                                 limit=int(request.args.get("limit", 20))))


# ---------------- 5) Institutional / insider ----------------
@api.get("/institutional/<ticker>")
def institutional_ep(ticker):
    return jsonify(institutional.get_ownership(ticker))


# ---------------- 6) Macro ----------------
@api.get("/macro")
def macro_ep():
    return jsonify(macro.get_macro())


# ---------------- 7) Sector ----------------
@api.get("/sectors")
def sectors_ep():
    return jsonify(macro.sector_performance(request.args.get("market", "th")))


# ---------------- 8) Daily report ----------------
@api.get("/daily-report")
def daily_report_ep():
    return jsonify(daily_report.generate(request.args.get("market", "th"),
                                         int(request.args.get("top", 5))))


# ---------------- 9) Portfolio ----------------
@api.get("/portfolio")
def portfolio_get():
    return jsonify(portfolio.summary())


@api.post("/portfolio")
def portfolio_add():
    a = _args()
    return jsonify(portfolio.add_holding(
        a.get("ticker"), a.get("shares"), a.get("buy_price"),
        a.get("buy_date"), a.get("note")))


@api.delete("/portfolio/<int:hid>")
def portfolio_delete(hid):
    return jsonify(portfolio.delete_holding(hid))


# ---------------- 10) Backtest ----------------
@api.post("/backtest")
def backtest_ep():
    a = _args()
    return jsonify(backtest.run(
        a.get("ticker"), a.get("strategy", "sma_cross"),
        a.get("period", "5y"), a.get("params", {})))


# ---------------- 11) Alerts + LINE ----------------
@api.get("/alerts")
def alerts_list():
    return jsonify({"alerts": alerts.list_alerts()})


@api.post("/alerts")
def alerts_add():
    a = _args()
    return jsonify(alerts.add_alert(a.get("ticker"), a.get("condition"),
                                    a.get("target"), a.get("note")))


@api.delete("/alerts/<int:aid>")
def alerts_delete(aid):
    return jsonify(alerts.delete_alert(aid))


@api.post("/alerts/check")
def alerts_check():
    return jsonify(alerts.check_alerts(send=_args().get("send", True)))


@api.post("/line/test")
def line_test():
    msg = _args().get("message", "🚀 ทดสอบการแจ้งเตือนจาก Stock Analysis App")
    return jsonify(alerts.send_line(msg))


# ---------------- 12) AI Advisory ----------------
@api.post("/advisory")
def advisory():
    return jsonify(ai_advisory.ask(_args().get("question", "")))


# ---------------- 13) Risk management ----------------
@api.get("/risk")
def risk_get():
    return jsonify(risk.portfolio_risk())


@api.post("/risk/position-size")
def position_size():
    a = _args()
    return jsonify(risk.position_size(
        a.get("account_size"), a.get("risk_pct"),
        a.get("entry"), a.get("stop_loss")))


# ---------------- 14) Overall score ----------------
@api.get("/score/<ticker>")
def score_ep(ticker):
    return jsonify(scoring.overall(ticker))


# ---------------- watchlist ----------------
@api.get("/watchlist")
def watchlist_get():
    items = query("SELECT * FROM watchlist ORDER BY created_at DESC")
    return jsonify({"watchlist": items})


@api.post("/watchlist")
def watchlist_add():
    t = stock_data.normalize_ticker(_args().get("ticker", ""))
    if t:
        execute("INSERT OR IGNORE INTO watchlist(ticker) VALUES(?)", (t,))
    return jsonify({"ok": bool(t), "ticker": t})


@api.delete("/watchlist/<ticker>")
def watchlist_delete(ticker):
    execute("DELETE FROM watchlist WHERE ticker = ?", (stock_data.normalize_ticker(ticker),))
    return jsonify({"ok": True})


# ---------------- defaults / config ----------------
@api.get("/defaults")
def defaults():
    return jsonify({
        "th": Config.DEFAULT_TH_TICKERS,
        "us": Config.DEFAULT_US_TICKERS,
        "line_configured": bool(Config.LINE_CHANNEL_TOKEN or Config.LINE_NOTIFY_TOKEN),
        "ai_mode": ai_advisory._mode(),
    })
