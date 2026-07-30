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
    alerts, daily_report, ai_advisory, gdelt, correlation, news_backtest, crisis,
    selfcheck, volume_profile, strategy_lab, volume_edge,
    trailing, freedom,
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
    market = a.pop("market", "us")
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
    # lang: auto (เลือกตามหุ้น) | th | en | both
    return jsonify(news.get_news(query=request.args.get("q", ""),
                                 ticker=request.args.get("ticker", ""),
                                 limit=int(request.args.get("limit", 20)),
                                 lang=request.args.get("lang", "auto")))


# ---------------- 5) Institutional / insider ----------------
@api.get("/institutional/<ticker>")
def institutional_ep(ticker):
    return jsonify(institutional.get_ownership(ticker))


# ---------------- 6) Macro ----------------
@api.get("/macro")
def macro_ep():
    return jsonify(macro.get_macro(request.args.get("market", "")))


# ---------------- 7) Sector ----------------
@api.get("/sectors")
def sectors_ep():
    return jsonify(macro.sector_performance(request.args.get("market", "us")))


# ---------------- 8) Daily report ----------------
@api.get("/daily-report")
def daily_report_ep():
    return jsonify(daily_report.generate(request.args.get("market", "us"),
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


# ---------------- 15) ข่าวโลก GDELT + ลูกโลก 3D ----------------
@api.get("/world/points")
def world_points_ep():
    """จุดข่าวพร้อมพิกัดสำหรับปักบนลูกโลก (ระบุ theme= เพื่อกรองธีมเดียว)"""
    theme = request.args.get("theme", "")
    timespan = request.args.get("timespan", "24h")
    if theme:
        return jsonify(gdelt.world_points(theme=theme, timespan=timespan))
    return jsonify(gdelt.all_theme_points(timespan=timespan))


@api.get("/world/themes")
def world_themes_ep():
    """รายชื่อธีมข่าวโลกทั้งหมด + สี"""
    return jsonify({"themes": [
        {"key": k, "label": v[0], "query": v[1], "color": v[2]}
        for k, v in Config.WORLD_THEMES.items()
    ]})


@api.get("/world/signals")
def world_signals_ep():
    """tone ล่าสุดของแต่ละธีมข่าวโลก (ข่าวดี/ร้ายผิดปกติแค่ไหน)"""
    return jsonify(gdelt.theme_signals(request.args.get("timespan", "7d")))


@api.get("/world/news")
def world_news_ep():
    q = request.args.get("q", "")
    theme = request.args.get("theme", "")
    if theme and not q:
        q = gdelt.theme_query(theme)
    return jsonify(gdelt.articles(q or "stock market",
                                  limit=int(request.args.get("limit", 20)),
                                  timespan=request.args.get("timespan", "24h")))


@api.get("/world/tone")
def world_tone_ep():
    """timeline ของ tone (ใช้วาดกราฟข่าว vs ราคา)"""
    theme = request.args.get("theme", "")
    q = gdelt.theme_query(theme) if theme else request.args.get("q", "")
    days = int(request.args.get("days", Config.LEARN_WINDOW_DAYS))
    return jsonify(gdelt.tone_timeline(q, timespan=f"{days}d"))


# ---------------- 16) Learning engine (หาจุดเชื่อม ข่าว ↔ ราคา) ----------------
@api.get("/learn/status")
def learn_status_ep():
    return jsonify(correlation.status())


@api.post("/learn/snapshot")
def learn_snapshot_ep():
    """เก็บภาพนิ่งของข่าว+ราคา ณ ตอนนี้ลงคลังข้อมูลสะสม"""
    return jsonify(correlation.snapshot())


@api.get("/learn/analyze/<ticker>")
def learn_analyze_ep(ticker):
    """หาความสัมพันธ์ ข่าวโลก/มหภาค ↔ ผลตอบแทนของหุ้นตัวนี้"""
    days = int(request.args.get("days", Config.LEARN_WINDOW_DAYS))
    return jsonify(correlation.analyze(ticker, days=days))


@api.get("/learn/catalyst/<ticker>")
def learn_catalyst_ep(ticker):
    """ข่าวโลกตอนนี้ กำลังหนุนหรือกดดันหุ้นตัวนี้ (จากความรู้ที่เรียนมา)"""
    return jsonify(correlation.catalyst_signal(ticker))


@api.post("/learn/watchlist")
def learn_watchlist_ep():
    """สั่งเรียนรู้หุ้นใน watchlist + พอร์ต ทีเดียวทั้งหมด"""
    a = _args()
    return jsonify(correlation.learn_watchlist(
        days=int(a.get("days") or Config.LEARN_WINDOW_DAYS),
        limit=int(a.get("limit") or 15)))


@api.get("/learn/backtest/<ticker>")
def learn_backtest_ep(ticker):
    """
    ทดสอบว่า "ถ้าเทรดตามสัญญาณข่าวจริง ๆ จะได้กำไรไหม"
    แบ่งข้อมูล train/test — หาสัญญาณจาก train เทรดใน test เท่านั้น
    """
    return jsonify(news_backtest.run(
        ticker,
        days=int(request.args.get("days", 540)),
        train_frac=float(request.args.get("train_frac", 0.6)),
        fee_pct=float(request.args.get("fee", news_backtest.DEFAULT_FEE_PCT)),
    ))


# ---------------- 17) เรียนรู้จากวิกฤตในอดีต + สัญญาณเตือนล่วงหน้า ----------------
@api.get("/crisis/list")
def crisis_list_ep():
    """รายชื่อวิกฤตสำคัญที่ใช้ศึกษา"""
    return jsonify({"crises": crisis.CRISES})


@api.get("/crisis/impact/<ticker>")
def crisis_impact_ep(ticker):
    """วิกฤตแต่ละครั้งทำให้หุ้นตัวนี้ร่วงแค่ไหน ฟื้นนานเท่าไหร่"""
    return jsonify(crisis.impact(ticker, request.args.get("benchmark", "^GSPC")))


@api.get("/crisis/signals")
def crisis_signals_ep():
    """สัญญาณเตือนล่วงหน้า — ก่อนวิกฤตหน้าตาเป็นยังไง วันนี้อยู่ตรงไหน"""
    return jsonify(crisis.warning_signals())


@api.get("/learn/links")
def learn_links_ep():
    """ความสัมพันธ์ทั้งหมดที่เรียนรู้เก็บไว้แล้ว"""
    return jsonify(correlation.learned(request.args.get("target", ""),
                                       int(request.args.get("limit", 50))))


# ---------------- 19) Volume Profile (ติดอาวุธจาก volume-edge) ----------------
@api.get("/volume-profile/<ticker>")
def volume_profile_ep(ticker):
    """Volume Profile: POC / Value Area / HVN / LVN + histogram สำหรับวาดกราฟ"""
    return jsonify(volume_profile.build_profile(ticker))


@api.get("/volume-setup/<ticker>")
def volume_setup_ep(ticker):
    """ดูว่าหุ้นตัวนี้เข้า setup VAB/VAR ตอนนี้ไหม + จุดเข้า/ตัดขาดทุน/เป้า + เหตุผลไทย"""
    return jsonify(volume_profile.detect_setup(ticker))


@api.post("/volume-scan")
def volume_scan_ep():
    """สแกนหาหุ้นที่กำลังเข้า setup VAB/VAR ตอนนี้ (จาก watchlist หรือ universe)"""
    a = _args()
    source = a.get("source", "watchlist")
    if source == "watchlist":
        tickers = [w["ticker"] for w in query("SELECT ticker FROM watchlist")]
        if not tickers:
            tickers = Config.DEFAULT_US_TICKERS
    elif source == "th":
        from services.universe import get_universe
        tickers = get_universe("th")
    elif source == "us":
        from services.universe import get_universe
        tickers = get_universe("us")
    else:
        tickers = a.get("tickers") or Config.DEFAULT_US_TICKERS
    return jsonify(volume_profile.scan_setups(
        tickers, max_scan=int(a.get("max_scan", volume_profile.SCAN_CAP))))


# ---------------- 20) Strategy Lab — โรงงานทดสอบกลยุทธ์หลายตระกูล ----------------
@api.get("/lab/strategies")
def lab_strategies_ep():
    """รายชื่อกลยุทธ์ทั้งหมดในแล็บ + สถานะ (รันได้/มีหลักฐานแล้ว/อยู่ในแผน)"""
    return jsonify(strategy_lab.list_strategies())


@api.get("/lab/run/<key>/<ticker>")
def lab_run_ep(key, ticker):
    """รันกลยุทธ์ 1 ตัวกับหุ้น 1 ตัว ผ่านประตูความซื่อสัตย์ (walk-forward + ค่าธรรมเนียม)"""
    return jsonify(strategy_lab.run(
        key, ticker,
        days=int(request.args.get("days", strategy_lab.DEFAULT_DAYS)),
        train_frac=float(request.args.get("train_frac", 0.6)),
        fee_pct=float(request.args.get("fee", strategy_lab.DEFAULT_FEE_PCT)),
    ))


@api.post("/lab/league")
def lab_league_ep():
    """จัดอันดับทุกกลยุทธ์ข้ามตะกร้าหุ้น — ตัวไหนน่าตามต่อ ตัวไหนตกรอบ"""
    a = _args()
    tickers = a.get("tickers")
    if a.get("source") == "watchlist":
        tickers = [w["ticker"] for w in query("SELECT ticker FROM watchlist")] or None
    return jsonify(strategy_lab.league(
        tickers=tickers,
        days=int(a.get("days") or strategy_lab.DEFAULT_DAYS),
        include=a.get("include")))


# ---------------- 21) สะพานเชื่อมระบบเทรด MT5 ที่บ้าน (volume-edge) ----------------
@api.get("/ve/overview")
def ve_overview_ep():
    """ทุกอย่างของหน้าพอร์ต MT5 ในคำขอเดียว (สถานะ + ไม้เปิด + สัญญาณ + สถิติ)"""
    return jsonify(volume_edge.overview())


@api.get("/ve/status")
def ve_status_ep():
    return jsonify(volume_edge.status())


@api.get("/ve/positions")
def ve_positions_ep():
    """ไม้จริงใน MT5 + เหตุผลตอนเข้า + มุมมองข่าวโลกของ NEBULA ต่อไม้นั้น"""
    return jsonify(volume_edge.positions())


@api.get("/ve/trades")
def ve_trades_ep():
    return jsonify(volume_edge.trades(
        limit=int(request.args.get("limit", 50)),
        status_filter=request.args.get("status", "all")))


@api.get("/ve/signals")
def ve_signals_ep():
    return jsonify(volume_edge.signals(int(request.args.get("limit", 40))))


@api.get("/ve/stats")
def ve_stats_ep():
    return jsonify(volume_edge.setup_stats())


@api.get("/ve/equity")
def ve_equity_ep():
    return jsonify(volume_edge.equity(int(request.args.get("limit", 400))))


@api.get("/ve/screener")
def ve_screener_ep():
    return jsonify(volume_edge.screener_latest())


# ---------------- 18) ตรวจระบบ ----------------
@api.get("/selfcheck")
def selfcheck_ep():
    """ตรวจว่าแหล่งข้อมูลภายนอกทุกตัวใช้งานได้จริงไหม (ใช้เวลาสักครู่)"""
    syms = request.args.get("symbols", "1") == "1"
    res = selfcheck.run(include_symbols=syms)
    if request.args.get("format") == "text":
        return selfcheck.as_text(res), 200, {"Content-Type": "text/plain; charset=utf-8"}
    return jsonify(res)


# ---------------- defaults / config ----------------
@api.get("/defaults")
def defaults():
    return jsonify({
        "th": Config.DEFAULT_TH_TICKERS,
        "us": Config.DEFAULT_US_TICKERS,
        "funds": Config.DEFAULT_FUND_TICKERS,
        "line_configured": bool(Config.LINE_CHANNEL_TOKEN or Config.LINE_NOTIFY_TOKEN),
        "ai_mode": ai_advisory._mode(),
    })


# ---------------- 18) Trailing stop ----------------
@api.get("/trailing/portfolio")
def trailing_portfolio_ep():
    """จุดตัดขาดทุนแบบเลื่อนตามของทุกไม้ในพอร์ต"""
    return jsonify(trailing.portfolio())


@api.get("/trailing/<ticker>")
def trailing_ticker_ep(ticker):
    """
    คำนวณให้หุ้นตัวเดียว — ระบุราคาที่เข้าและวันที่เข้าได้
    ใช้ตอนอยากลองดูก่อนซื้อจริง หรือกับไม้ที่ไม่ได้บันทึกไว้ในพอร์ต
    """
    try:
        entry = float(request.args.get("entry") or 0)
    except ValueError:
        entry = 0
    if entry <= 0:
        return jsonify({"ok": False, "error": "ต้องระบุราคาที่เข้า (entry)"}), 400
    try:
        mult = float(request.args.get("mult") or trailing.DEFAULT_MULT)
    except ValueError:
        mult = trailing.DEFAULT_MULT
    return jsonify(trailing.for_ticker(ticker, entry,
                                       request.args.get("date", ""), mult))


# ---------------- 19) แผนอิสรภาพ ----------------
def _money(name, default=0.0):
    try:
        return max(0.0, float(request.args.get(name) or default))
    except ValueError:
        return default


@api.get("/freedom/plan")
def freedom_plan_ep():
    """
    แผนทบต้นจากผลงานจริง — ไม่ให้กรอกผลตอบแทนเอง เพราะคนมักกรอกตัวเลขที่อยากได้
    """
    try:
        years = int(request.args.get("years") or 10)
    except ValueError:
        years = 10
    return jsonify(freedom.plan(
        start=_money("start"), monthly_add=_money("monthly"),
        target=_money("target"), years=years,
        source=request.args.get("source", "auto")))


@api.get("/freedom/performance")
def freedom_performance_ep():
    """สรุปผลงานจริงอย่างเดียว (ไม่ต้องจำลองอนาคต)"""
    data = freedom.real_returns(request.args.get("source", "auto"))
    if not data.get("ok"):
        return jsonify({"ok": False, "error": data["error"],
                        "how_to_fix": data.get("how_to_fix")})
    return jsonify({"ok": True, "source": data["source"],
                    "source_label": data["label"],
                    "performance": freedom.stats_from_returns(data["returns"])})
