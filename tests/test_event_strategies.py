"""
ทดสอบกลยุทธ์ตระกูล "เหตุการณ์" — PEAD (งบดีกว่าคาด) และ insider (ผู้บริหารซื้อ)

ความผิดพลาดที่ทำให้ backtest สวยแบบหลอก ๆ และเทสชุดนี้กันไว้:
  1. เข้าซื้อ "วันเดียวกับเหตุการณ์" = มองเห็นข้อมูลที่ตอนนั้นยังไม่มีใครรู้
     (งบออกหลังตลาดปิด · รายการ insider ถูกรายงานช้ากว่าวันที่ทำจริง)
  2. ใช้งบที่ "ยังไม่ประกาศ" ซึ่ง Yahoo ส่งมาด้วย = เห็นอนาคตตรง ๆ
  3. จูนพารามิเตอร์บนช่วง test = เลือกคำตอบหลังเห็นเฉลย
"""
import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import events_data as E, strategy_lab as L  # noqa: E402


# ---------------------------------------------------------------------------
# 1) แปลงข้อมูลดิบจาก Yahoo
# ---------------------------------------------------------------------------
class FakeDF:
    """DataFrame ปลอมแบบพอใช้ — มี columns / empty / iterrows"""
    def __init__(self, rows, columns, index=None):
        self._rows = rows
        self.columns = columns
        self._index = index if index is not None else list(range(len(rows)))
        self.empty = not rows

    def iterrows(self):
        return zip(self._index, self._rows)


def _fake_yf(monkeypatch, *, earnings=None, insider=None, boom=False):
    class FakeTicker:
        def __init__(self, t): pass

        def get_earnings_dates(self, limit=24):
            if boom:
                raise RuntimeError("network down")
            return earnings

        @property
        def insider_transactions(self):
            if boom:
                raise RuntimeError("network down")
            return insider

    monkeypatch.setattr(E, "yf", type("M", (), {"Ticker": FakeTicker}))
    monkeypatch.setattr(E, "_YF_OK", True)
    store = {}
    monkeypatch.setattr(E, "cache_get", lambda k: store.get(k))
    monkeypatch.setattr(E, "cache_set", lambda k, v, ttl: store.__setitem__(k, v))


def test_future_earnings_rows_are_dropped(monkeypatch):
    """
    Yahoo ส่งงบ "ที่ยังไม่ประกาศ" มาด้วย ถ้าเอามาใช้ = เห็นอนาคต
    backtest จะสวยแบบไม่มีความหมาย
    """
    future = (dt.date.today() + dt.timedelta(days=30)).isoformat()
    past = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    df = FakeDF(
        rows=[{"Surprise(%)": 5.0}, {"Surprise(%)": 3.0}],
        columns=["Surprise(%)"],
        index=[future, past])
    _fake_yf(monkeypatch, earnings=df)
    got = E.earnings_surprises("AAPL")
    assert [e["day"] for e in got["events"]] == [past]


def test_surprise_computed_when_yahoo_gives_only_estimate_and_actual(monkeypatch):
    past = (dt.date.today() - dt.timedelta(days=10)).isoformat()
    df = FakeDF(rows=[{"EPS Estimate": 2.0, "Reported EPS": 2.4}],
                columns=["EPS Estimate", "Reported EPS"], index=[past])
    _fake_yf(monkeypatch, earnings=df)
    got = E.earnings_surprises("AAPL")
    assert got["events"][0]["surprise_pct"] == 20.0


def test_too_few_earnings_reports_honestly(monkeypatch):
    past = (dt.date.today() - dt.timedelta(days=10)).isoformat()
    df = FakeDF(rows=[{"Surprise(%)": 5.0}], columns=["Surprise(%)"], index=[past])
    _fake_yf(monkeypatch, earnings=df)
    got = E.earnings_surprises("PTT.BK")
    assert got["ok"] is False and "ต้องการ" in got["error"]


def test_network_failure_is_reported_not_swallowed(monkeypatch):
    _fake_yf(monkeypatch, boom=True)
    got = E.earnings_surprises("AAPL")
    assert got["ok"] is False and got["error"]


def test_insider_keeps_buys_and_drops_sales(monkeypatch):
    past = (dt.date.today() - dt.timedelta(days=5)).isoformat()
    df = FakeDF(
        rows=[{"Text": "Purchase at price 10", "Start Date": past, "Shares": 100},
              {"Text": "Sale at price 12", "Start Date": past, "Shares": 50},
              {"Text": "Conversion of derivative", "Start Date": past, "Shares": 5}],
        columns=["Text", "Start Date", "Shares"])
    _fake_yf(monkeypatch, insider=df)
    got = E.insider_buys("AAPL")
    assert len(got["events"]) == 1 and got["events"][0]["shares"] == 100


# ---------------------------------------------------------------------------
# 2) หัวใจ: ห้ามเข้าซื้อวันเดียวกับเหตุการณ์
# ---------------------------------------------------------------------------
DAYS = [f"2026-01-{d:02d}" for d in range(1, 21)]


def test_entry_is_the_day_after_the_event_not_the_same_day():
    pos = L._hold_after_events(DAYS, ["2026-01-05"], hold=3)
    assert pos["2026-01-05"] == 0, "วันเกิดเหตุยังห้ามถือ (ข่าวออกหลังตลาดปิด)"
    assert pos["2026-01-06"] == 1
    assert pos["2026-01-08"] == 1
    assert pos["2026-01-09"] == 0, "ครบ 3 วันแล้วต้องออก"


def test_event_on_a_non_trading_day_still_enters_next_trading_day():
    """เหตุการณ์ตกวันหยุด ต้องเข้าวันทำการถัดไป ไม่ใช่หายไปเฉย ๆ"""
    pos = L._hold_after_events(DAYS, ["2026-01-04T18:00"], hold=2)
    assert pos["2026-01-05"] == 1


def test_overlapping_events_do_not_double_count():
    pos = L._hold_after_events(DAYS, ["2026-01-05", "2026-01-06"], hold=3)
    assert set(pos.values()) <= {0, 1}


def test_no_events_means_never_in_the_market():
    pos = L._hold_after_events(DAYS, [], hold=5)
    assert sum(pos.values()) == 0


# ---------------------------------------------------------------------------
# 3) จูนพารามิเตอร์ต้องใช้ช่วง train เท่านั้น
# ---------------------------------------------------------------------------
def test_tuning_never_looks_at_the_test_period(monkeypatch):
    """
    ฝังกำไรก้อนใหญ่ไว้ "เฉพาะช่วง test" ถ้าตัวจูนแอบมอง มันจะเลือกค่าที่
    จับกำไรก้อนนั้น — เทสนี้จับได้ว่ามันไม่ได้มอง
    """
    rets = {d: 0.0 for d in DAYS}
    for d in DAYS[14:]:
        rets[d] = 0.5                       # กำไรมหาศาล อยู่ในช่วง test ล้วน ๆ
    train = set(DAYS[:14])

    grids = [
        {"hold": 1, "events": ["2026-01-01"]},    # ไม่แตะช่วง test
        {"hold": 12, "events": ["2026-01-08"]},   # ลากยาวเข้าไปกินช่วง test
    ]
    best = L._tune_on_train(DAYS, rets, train, [], grids, fee_pct=0.0)
    assert best["combo"]["hold"] == 1, "ต้องไม่เลือกตัวที่ได้ดีเพราะช่วง test"


# ---------------------------------------------------------------------------
# 4) เชื่อมเข้า Strategy Lab
# ---------------------------------------------------------------------------
def test_both_strategies_are_runnable_now():
    for key in ("pead", "insider"):
        assert L.STRATEGIES[key]["runnable"] is True
        assert not L.STRATEGIES[key].get("planned")


def test_run_reports_clearly_when_data_is_missing(monkeypatch):
    """หุ้นไทยไม่มีค่าคาดการณ์ใน Yahoo — ต้องบอกเหตุผลตรง ๆ ไม่ใช่เงียบหรือพัง"""
    monkeypatch.setattr(L, "_closes", lambda t, d: (DAYS, [10.0] * len(DAYS)))
    monkeypatch.setattr(L, "MIN_RET_DAYS", 5)
    monkeypatch.setattr(E, "earnings_surprises",
                        lambda t: {"ok": False, "error": "ไม่มีค่าคาดการณ์", "events": []})
    monkeypatch.setattr(L.events_data, "earnings_surprises",
                        lambda t: {"ok": False, "error": "ไม่มีค่าคาดการณ์", "events": []})
    res = L.run("pead", "PTT.BK", days=300)
    assert res["ok"] is False and "ไม่มีค่าคาดการณ์" in res["error"]


def test_params_say_where_the_data_came_from(monkeypatch):
    """ผู้ใช้ต้องรู้ว่าตัวเลขมาจากไหนและจูนด้วยอะไร ไม่ใช่เชื่อลอย ๆ"""
    evs = [{"day": DAYS[i], "surprise_pct": 9.0} for i in (1, 3, 5, 7)]
    monkeypatch.setattr(L.events_data, "earnings_surprises",
                        lambda t: {"ok": True, "events": evs})
    rets = {d: 0.01 for d in DAYS}
    pos, params = L._positions_pead("AAPL", DAYS, rets, set(DAYS[:14]), 0.1)
    assert pos is not None
    assert params["tuned_on"] == "ช่วง train เท่านั้น"
    assert "Yahoo" in params["source"]
    assert params["events_used"] == 4
