"""
ชุดทดสอบแล็บกลยุทธ์ (Strategy Lab)

รันด้วย:  python -m pytest tests/ -v
(ไม่ต้องต่อเน็ต — monkeypatch ราคา/ข่าวเป็นข้อมูลสังเคราะห์ที่รู้คำตอบล่วงหน้า)

สิ่งที่ต้องพิสูจน์
---------------
1. เครื่องจำลอง position คิดค่าธรรมเนียม/กำไรถูกต้องเป๊ะ (คำนวณมือเทียบ)
2. โมเมนตัมต้อง "หนี" ขาลงใหญ่ได้ (ชนะ buy & hold ในตลาดที่พังตอนท้าย)
3. โมเมนตัม/เทรนด์ห้ามดูอนาคต (position วันนี้ใช้ราคาถึงเมื่อวานเท่านั้น)
4. ข่าวพุ่ง: เกณฑ์มาจากช่วง train เท่านั้น และจับ drift ที่ปลูกไว้ได้
5. league จัดอันดับ + สถานะไม่โกหก
"""
import datetime as dt
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LEARN_AUTO", "0")
os.environ.setdefault("DB_PATH", "/tmp/nebula_test.db")

from database import init_db  # noqa: E402
from services import strategy_lab as L, stock_data, gdelt  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _db():
    init_db()
    yield


def _trading_days(n, start=dt.date(2022, 1, 3)):
    """วันทำการ (จันทร์-ศุกร์) n วัน"""
    out = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _fake_history(dates, closes):
    def fake(ticker, period="1y", interval="1d"):
        return {"candles": [{"date": d, "close": c} for d, c in zip(dates, closes)]}
    return fake


# ---------------------------------------------------------------------------
# 1) เครื่องจำลอง position — คำนวณมือเทียบทุกตัวเลข
# ---------------------------------------------------------------------------
def test_simulate_positions_fees_and_trades_exact():
    dates = _trading_days(6)
    # ถือวัน 2-3 (ผลตอบแทน +2% แล้ว +1%) นอกนั้นถือเงินสด
    rets = {dates[0]: 5.0, dates[1]: 2.0, dates[2]: 1.0,
            dates[3]: -4.0, dates[4]: 3.0, dates[5]: -1.0}
    pos = {dates[1]: 1, dates[2]: 1}
    fee = 0.1

    out = L._simulate_positions(dates, rets, pos, fee)

    f = 1 - fee / 100
    expected_equity = f * 1.02 * 1.01 * f          # เข้า -> +2% -> +1% -> ออก
    # กำไรต่อไม้วัดจากหลังหักค่าธรรมเนียมขาเข้าแล้ว จึงโดนเฉพาะขาออก
    expected_trade = 1.02 * 1.01 * f - 1
    assert out["num_trades"] == 1
    assert math.isclose(out["total_return_pct"], (expected_equity - 1) * 100, abs_tol=0.02)
    assert math.isclose(out["avg_trade_pct"], expected_trade * 100, abs_tol=0.02)
    assert out["win_rate"] == 100.0
    # ถือ 2 วันจาก 6 วัน
    assert math.isclose(out["exposure_pct"], 2 / 6 * 100, abs_tol=0.1)


def test_simulate_positions_open_position_closed_at_end():
    dates = _trading_days(3)
    rets = {d: 1.0 for d in dates}
    pos = {dates[2]: 1}                            # เปิดวันสุดท้าย ยังไม่ทันปิด
    out = L._simulate_positions(dates, rets, pos, 0.1)
    assert out["num_trades"] == 1                  # ต้องบังคับปิดตอนจบ (พร้อมค่าธรรมเนียม)


# ---------------------------------------------------------------------------
# 2) โมเมนตัมต้องหนีขาลงใหญ่ได้
# ---------------------------------------------------------------------------
def test_momentum_escapes_crash_and_beats_buyhold(monkeypatch):
    """
    ตลาดสังเคราะห์: ขึ้น 0.3%/วัน 500 วัน แล้วพัง -0.5%/วัน 200 วัน
    buy & hold ในช่วง test เจ็บหนัก · โมเมนตัมต้องออกหลังพีคไม่นานแล้วรอด
    """
    n_up, n_down = 500, 200
    dates = _trading_days(n_up + n_down)
    closes, p = [], 100.0
    for i in range(len(dates)):
        p *= 1.003 if i < n_up else 0.995
        closes.append(p)

    monkeypatch.setattr(stock_data, "get_history", _fake_history(dates, closes))
    monkeypatch.setattr(stock_data, "normalize_ticker", lambda t: t)

    res = L.run("momentum", "FAKE", days=900)
    assert res["ok"], res.get("error")
    oos = res["out_of_sample"]["total_return_pct"]
    bh = res["buyhold"]["total_return_pct"]
    assert bh < -30                                # ตลาดช่วง test พังจริง
    assert oos > bh + 10                           # โมเมนตัมหนีทัน ชนะขาดลอย
    assert res["out_of_sample"]["exposure_pct"] < 90   # ไม่ได้ถือตลอด (ออกแล้วจริง)


def test_momentum_no_lookahead(monkeypatch):
    """
    position ของ 'วันสุดท้าย' ต้องไม่เปลี่ยน แม้ราคาวันสุดท้ายพุ่ง 10 เท่า
    (ถ้าเปลี่ยน = แอบดูราคาวันนี้ก่อนตัดสินใจวันนี้ = โกง)
    """
    dates = _trading_days(400)
    base = [100.0 * (0.999 ** i) for i in range(400)]   # ขาลงอ่อน ๆ -> ไม่ถือ

    monkeypatch.setattr(stock_data, "normalize_ticker", lambda t: t)

    monkeypatch.setattr(stock_data, "get_history", _fake_history(dates, base))
    pos_a, _ = L._positions_momentum(dates, base)

    pumped = base[:-1] + [base[-1] * 10]                # ปั๊มเฉพาะวันสุดท้าย
    pos_b, _ = L._positions_momentum(dates, pumped)

    assert pos_a.get(dates[-1]) == pos_b.get(dates[-1])


def test_trend_positions_follow_sma(monkeypatch):
    """ขาขึ้นยาว: หลัง warmup ต้องถือ · ขาลงยาวลึก: ต้องถือเงินสด"""
    n = 500
    dates = _trading_days(n)
    up = [100.0 * (1.002 ** i) for i in range(n)]
    pos_up, _ = L._positions_trend(dates, up)
    assert all(v == 1 for d, v in pos_up.items())       # เหนือ SMA200 ตลอด

    down = [100.0 * (0.997 ** i) for i in range(n)]
    pos_dn, _ = L._positions_trend(dates, down)
    assert all(v == 0 for d, v in pos_dn.items())       # ใต้ SMA200 ตลอด


# ---------------------------------------------------------------------------
# 3) ข่าวพุ่ง — เกณฑ์จาก train เท่านั้น + จับ drift ที่ปลูกไว้ได้
# ---------------------------------------------------------------------------
def _plant_news_world(monkeypatch, spike_dates, n_days=760, drift=1.5):
    """
    โลกสังเคราะห์: ราคาซึมลง -0.1%/วัน ยกเว้น 3 วันทำการหลังวันข่าวพุ่ง
    ราคาขึ้น drift%/วัน · ปริมาณข่าวปกติ 1.0-1.6 · วันพุ่ง = 9.0
    โทนวันพุ่ง = +3 (ดีกว่าค่ากลาง 0)
    """
    dates = _trading_days(n_days)
    didx = {d: i for i, d in enumerate(dates)}

    boosted = set()
    for sd in spike_dates:
        i = didx[sd]
        boosted.update(dates[i + 1:i + 4])              # 3 วันทำการถัดไป

    closes, p = [], 100.0
    for d in dates:
        p *= (1 + drift / 100) if d in boosted else 0.999
        closes.append(p)

    spikes = set(spike_dates)
    vol = {d: (9.0 if d in spikes else 1.0 + (i % 7) * 0.1)
           for i, d in enumerate(dates)}
    tone = {d: (3.0 if d in spikes else 0.0) for d in dates}

    monkeypatch.setattr(stock_data, "get_history", _fake_history(dates, closes))
    monkeypatch.setattr(stock_data, "normalize_ticker", lambda t: t)
    monkeypatch.setattr(gdelt, "volume_timeline",
                        lambda q, timespan="": {"ok": True, "series": vol})
    monkeypatch.setattr(gdelt, "tone_timeline",
                        lambda q, timespan="": {"ok": True, "series": tone})
    return dates


def test_news_velocity_catches_planted_drift(monkeypatch):
    # ปลูกข่าวพุ่งทุก ๆ 60 วัน ทั้งช่วง train (60% แรก) และช่วง test (40% หลัง)
    all_dates = _trading_days(760)
    spikes = all_dates[50::60]
    _plant_news_world(monkeypatch, spikes)

    res = L.run("news_velocity", "FAKE", days=900)
    assert res["ok"], res.get("error")
    oos = res["out_of_sample"]
    assert oos["num_trades"] >= 2                       # มีสัญญาณในช่วง test จริง
    assert oos["total_return_pct"] > 3                  # จับ drift ที่ปลูกไว้ได้
    assert oos["total_return_pct"] > res["buyhold"]["total_return_pct"]
    assert res["verdict"]["level"] in ("good", "weak")
    # เกณฑ์ต้องมาจาก train: threshold อยู่ระหว่างค่าปกติกับวันพุ่ง (9.0)
    assert 1.0 < res["params"]["volume_threshold"] < 9.0


def test_news_velocity_quiet_news_no_trades(monkeypatch):
    """ไม่มีข่าวพุ่งเลย -> ห้ามเทรดมั่ว (จำนวนไม้ต้องเป็น 0)"""
    dates = _trading_days(760)
    closes = [100.0] * len(dates)
    vol = {d: 1.0 for d in dates}                       # เงียบสนิท เท่ากันทุกวัน
    tone = {d: 0.0 for d in dates}

    monkeypatch.setattr(stock_data, "get_history", _fake_history(dates, closes))
    monkeypatch.setattr(stock_data, "normalize_ticker", lambda t: t)
    monkeypatch.setattr(gdelt, "volume_timeline",
                        lambda q, timespan="": {"ok": True, "series": vol})
    monkeypatch.setattr(gdelt, "tone_timeline",
                        lambda q, timespan="": {"ok": True, "series": tone})

    res = L.run("news_velocity", "FAKE", days=900)
    assert res["ok"], res.get("error")
    # ปริมาณข่าวเท่ากันทุกวัน -> ทุกวัน "≥ threshold" แต่โทนไม่เคย > ค่ากลาง -> ไม่เทรด
    assert res["out_of_sample"]["num_trades"] == 0
    assert res["verdict"]["level"] == "unknown"         # เทรดน้อยไป ไม่ฟันธง


# ---------------------------------------------------------------------------
# 4) league — จัดอันดับและสถานะต้องไม่โกหก
# ---------------------------------------------------------------------------
def test_league_ranks_and_reports(monkeypatch):
    """โลกที่ตลาดพังตอนท้าย: momentum/trend ควรได้ edge บวก และถูกจัดอันดับ"""
    n_up, n_down = 500, 200
    dates = _trading_days(n_up + n_down)
    closes, p = [], 100.0
    for i in range(len(dates)):
        p *= 1.003 if i < n_up else 0.995
        closes.append(p)

    monkeypatch.setattr(stock_data, "get_history", _fake_history(dates, closes))
    monkeypatch.setattr(stock_data, "normalize_ticker", lambda t: t)

    res = L.league(tickers=["FAKE1", "FAKE2"], include=["momentum", "trend"])
    assert res["ok"]
    assert [r["key"] for r in res["rows"]]              # มีแถวครบ
    for row in res["rows"]:
        assert row["runs"] == 2
        assert row["avg_edge"] is not None and row["avg_edge"] > 0
        assert row["beat_market"] == 2
        assert row["status"]["level"] in ("follow", "mixed")
    # เรียงจาก edge มาก -> น้อย
    edges = [r["avg_edge"] for r in res["rows"]]
    assert edges == sorted(edges, reverse=True)


def test_league_status_fail_when_losing():
    st = L._status([-5.0, -2.0], {"bad": 2})
    assert st["level"] == "fail"
    st2 = L._status([], {})
    assert st2["level"] == "no_data"
    st3 = L._status([4.0, 6.0], {"good": 2})
    assert st3["level"] == "follow"


def test_list_strategies_registry():
    r = L.list_strategies()
    keys = {s["key"] for s in r["strategies"]}
    assert {"momentum", "trend", "news_velocity", "news_lag", "vp_setup"} <= keys
    runnable = {s["key"] for s in r["strategies"] if s["runnable"]}
    assert "vp_setup" not in runnable                   # VP ใช้ที่แท็บ Volume ไม่ใช่แล็บ
    assert {"momentum", "trend", "news_velocity", "news_lag"} <= runnable
