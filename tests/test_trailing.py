"""
ทดสอบ trailing stop

คุณสมบัติที่ "ต้องจริง" ไม่งั้นเครื่องมือนี้ไม่มีประโยชน์:
  1. เลื่อนขึ้นได้อย่างเดียว — ถ้าเลื่อนลงตามราคาด้วย มันจะไม่ล็อกกำไรอะไรเลย
     กลายเป็นตัดขาดทุนธรรมดาที่ขยับตามใจ ซึ่งแย่กว่าไม่มี
  2. ระยะต้องคิดจากความผันผวนจริงของหุ้นตัวนั้น (ATR) ไม่ใช่เปอร์เซ็นต์ตายตัว
  3. ข้อมูลไม่พอต้องบอกตรง ๆ ไม่ใช่คืนตัวเลขมั่ว ๆ ให้คนเอาไปตัดสินใจด้วยเงินจริง
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import trailing as T  # noqa: E402


def series(closes, spread=1.0):
    """สร้าง high/low รอบราคาปิด เพื่อให้มี ATR ที่คำนวณได้"""
    highs = [c + spread / 2 for c in closes]
    lows = [c - spread / 2 for c in closes]
    return highs, lows, closes


# ---------------------------------------------------------------------------
# 1) หัวใจ: ห้ามเลื่อนถอยหลัง
# ---------------------------------------------------------------------------
def test_stop_never_moves_down_when_price_falls_back():
    """
    ราคาวิ่งขึ้นแล้วย่อกลับ — จุดตัดต้องค้างอยู่ที่ระดับสูงสุดที่เคยเลื่อนไป
    ถ้ามันเลื่อนลงตาม = ไม่ได้ล็อกกำไรอะไรเลย เครื่องมือนี้ก็ไร้ความหมาย
    """
    up = [100 + i for i in range(40)]                 # 100 -> 139
    highs, lows, closes = series(up)
    at_peak = T.compute(highs, lows, closes, entry=100.0)

    back = up + [130, 125, 120]                        # ย่อกลับแรง
    highs2, lows2, closes2 = series(back)
    after_pullback = T.compute(highs2, lows2, closes2, entry=100.0)

    assert after_pullback["stop"] >= at_peak["stop"], "จุดตัดต้องไม่เลื่อนลง"


def test_stop_rises_as_price_makes_new_highs():
    flat = [100.0] * 30
    highs, lows, closes = series(flat)
    base = T.compute(highs, lows, closes, entry=100.0)

    rally = flat + [110, 120, 130]
    highs2, lows2, closes2 = series(rally)
    later = T.compute(highs2, lows2, closes2, entry=100.0)

    assert later["stop"] > base["stop"], "ราคาทำจุดสูงใหม่ จุดตัดต้องขยับขึ้น"


def test_reports_when_profit_is_locked_in():
    up = [100 + i * 2 for i in range(40)]              # ขึ้นแรงพอให้ stop > entry
    highs, lows, closes = series(up)
    r = T.compute(highs, lows, closes, entry=100.0)
    assert r["in_profit"] is True
    assert r["locked_pct"] > 0


def test_says_plainly_when_still_below_breakeven():
    flat = [100.0] * 30
    highs, lows, closes = series(flat)
    r = T.compute(highs, lows, closes, entry=100.0)
    assert r["in_profit"] is False
    assert r["locked_pct"] < 0
    assert "ยังไม่ถึงจุดคุ้มทุน" in T._advice(r)


# ---------------------------------------------------------------------------
# 2) ระยะต้องขึ้นกับความผันผวนจริง
# ---------------------------------------------------------------------------
def test_wilder_swinging_stock_gets_a_wider_stop():
    """
    หุ้นแกว่งแรงต้องได้ระยะห่างกว่า ไม่งั้นโดนเขี่ยออกจากการแกว่งปกติตลอด
    (นี่คือเหตุผลที่ไม่ใช้เปอร์เซ็นต์ตายตัว)
    """
    closes = [100.0] * 30
    calm = T.compute(*series(closes, spread=1.0), entry=100.0)
    wild = T.compute(*series(closes, spread=8.0), entry=100.0)
    assert wild["atr"] > calm["atr"]
    assert wild["stop"] < calm["stop"], "ตัวแกว่งแรงต้องตั้งจุดตัดห่างกว่า"


def test_multiplier_controls_the_distance():
    closes = [100.0] * 30
    tight = T.compute(*series(closes), entry=100.0, mult=1.0)
    loose = T.compute(*series(closes), entry=100.0, mult=4.0)
    assert loose["stop"] < tight["stop"]


def test_atr_counts_overnight_gaps():
    """
    ราคากระโดดข้ามวัน (gap) คือความเสี่ยงจริงที่ต้องนับ
    ถ้าใช้แค่ high-low ของวันจะประเมินความผันผวนต่ำเกินไป
    """
    closes = [100.0] * 20 + [130.0] * 5                # กระโดด 30 จุดข้ามคืน
    highs, lows, _ = series(closes, spread=0.5)
    atr = T._atr(highs, lows, closes)
    assert atr > 1.0, "ATR ต้องสะท้อนการกระโดดข้ามวัน ไม่ใช่แค่ช่วงในวัน"


# ---------------------------------------------------------------------------
# 3) ข้อมูลไม่พอ / ผิดรูป
# ---------------------------------------------------------------------------
def test_refuses_to_guess_when_history_is_too_short():
    closes = [100.0] * 5
    r = T.compute(*series(closes), entry=100.0)
    assert r["ok"] is False and "ไม่พอ" in r["error"]


def test_mismatched_series_are_rejected():
    r = T.compute([1, 2, 3], [1, 2], [1, 2, 3], entry=1.0)
    assert r["ok"] is False


def test_flags_positions_that_already_broke_the_stop():
    up = [100 + i for i in range(35)]
    crash = up + [80, 70]                              # ทะลุจุดตัดลงไปแล้ว
    r = T.compute(*series(crash), entry=100.0)
    assert r["already_hit"] is True
    assert "หลุดจุดตัด" in T._advice(r)


# ---------------------------------------------------------------------------
# 4) ต่อกับพอร์ตจริง
# ---------------------------------------------------------------------------
def test_one_broken_ticker_does_not_break_the_whole_table(monkeypatch):
    holdings = [{"ticker": "AAPL", "buy_price": 100.0, "buy_date": "2026-01-01",
                 "shares": 10},
                {"ticker": "BAD", "buy_price": 50.0, "buy_date": "", "shares": 5}]
    monkeypatch.setattr("database.query", lambda *a, **k: holdings)

    def fake_for_ticker(t, entry, entry_date="", mult=T.DEFAULT_MULT):
        if t == "BAD":
            raise RuntimeError("ดึงราคาไม่ได้")
        return {"ok": True, "ticker": t, "stop": 95.0, "in_profit": False,
                "locked_pct": -5.0, "price": 105.0}

    monkeypatch.setattr(T, "for_ticker", fake_for_ticker)
    res = T.portfolio()
    assert res["count"] == 2 and res["computed"] == 1
    assert any(not r["ok"] for r in res["rows"])


def test_result_states_it_does_not_place_orders(monkeypatch):
    """
    ต้องบอกให้ชัดว่านี่เป็นตัวเตือน ไม่ใช่ระบบส่งคำสั่งอัตโนมัติ
    เข้าใจผิดตรงนี้แล้วปล่อยไม้ทิ้งไว้ = เสียเงินจริง
    """
    monkeypatch.setattr("database.query", lambda *a, **k: [])
    res = T.portfolio()
    assert "ไม่ส่งคำสั่งซื้อขาย" in res["note"]
