"""
ทดสอบ "แผนอิสรภาพ" — เครื่องคำนวณทบต้นจากผลงานจริง

เครื่องคำนวณแบบนี้ถ้าทำผิดจะอันตรายกว่าไม่มี เพราะคนเอาไปวางแผนชีวิตจริง
เทสชุดนี้จึงล็อกเรื่องที่ "โกหกคนใช้ได้ง่ายที่สุด" ไว้:
  1. ใช้ค่าเฉลี่ยธรรมดาแทนค่าเฉลี่ยเรขาคณิต -> ตัวเลขสูงเกินจริงเสมอ
  2. ตอบเป็นตัวเลขเดียวเหมือนรู้อนาคต -> ต้องตอบเป็นช่วง
  3. ไม่มีข้อมูลจริงแล้วยังคำนวณให้ -> ต้องปฏิเสธและบอกวิธีแก้
  4. ผลเต้นทุกครั้งที่กด -> ตัดสินใจไม่ได้
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import freedom as F  # noqa: E402


def flat(n, r=0.001):
    return [r] * n


def varied(n, up=0.02, down=-0.015):
    """ผลตอบแทนที่มีขึ้นมีลง — ของจริงไม่มีทางคงที่ทุกวัน"""
    return [(up if i % 3 else down) for i in range(n)]


# ---------------------------------------------------------------------------
# 1) สถิติต้องเป็นความจริง
# ---------------------------------------------------------------------------
def test_uses_geometric_not_arithmetic_average():
    """
    กำไร 50% แล้วขาดทุน 50% = เหลือ 75% ไม่ใช่เท่าทุน
    ค่าเฉลี่ยธรรมดาจะบอก 0% ซึ่งโกหก — ต้องรายงานติดลบ
    """
    rets = [0.5, -0.5] * 40                     # 80 วัน
    got = F.stats_from_returns(rets)
    assert got["ok"] is True
    assert got["total_return_pct"] < 0, "ต้องรายงานว่าขาดทุนจริง"
    assert got["cagr_pct"] < 0


def test_reports_worst_drawdown_along_the_way():
    """ต้องบอกว่าระหว่างทางเคยขาดทุนหนักแค่ไหน — ตัวที่ทำให้คนเลิกกลางคัน"""
    rets = [0.01] * 40 + [-0.05] * 10 + [0.01] * 30
    got = F.stats_from_returns(rets)
    assert got["max_drawdown_pct"] < -15


def test_refuses_when_track_record_is_too_short():
    got = F.stats_from_returns(flat(20))
    assert got["ok"] is False and "ต้องการ" in got["error"]


def test_refuses_when_account_was_wiped_out():
    rets = flat(70, 0.001) + [-1.0]             # หมดพอร์ต
    got = F.stats_from_returns(rets)
    assert got["ok"] is False


# ---------------------------------------------------------------------------
# 2) การจำลองต้องตอบเป็นช่วง และคงที่
# ---------------------------------------------------------------------------
def test_projection_returns_a_range_not_a_single_number():
    # ต้องใช้ผลตอบแทนที่มีขึ้นมีลง เพราะถ้าคงที่ทุกวัน ทุกเส้นทางย่อมเท่ากัน
    # (นั่นถูกต้องแล้ว ไม่ใช่บั๊ก — ของจริงไม่มีวันคงที่)
    res = F.simulate(varied(200), start=100000, years=5, sims=300)
    assert res["ok"] is True
    assert res["p10"] <= res["median"] <= res["p90"], "ต้องเรียงจากแย่ไปดี"
    assert res["p10"] != res["p90"], "ตอบช่วงเดียวเท่ากันหมด = ไม่ได้จำลองจริง"


def test_same_input_gives_same_answer_every_time():
    """ผลเต้นทุกครั้งที่กด = ตัดสินใจไม่ได้ และดูเหมือนระบบมั่ว"""
    a = F.simulate(varied(200), start=100000, years=5, sims=300)
    b = F.simulate(varied(200), start=100000, years=5, sims=300)
    assert a["median"] == b["median"]


def test_monthly_contributions_increase_the_outcome():
    base = F.simulate(flat(200, 0.0003), start=100000, years=5, sims=300)
    more = F.simulate(flat(200, 0.0003), start=100000, monthly_add=10000,
                      years=5, sims=300)
    assert more["median"] > base["median"]
    assert more["invested_total"] > base["invested_total"]


def test_reports_the_chance_of_ending_up_worse_than_invested():
    """ต้องบอกโอกาสขาดทุน ไม่ใช่โชว์แต่กรณีที่สวย"""
    losing = [-0.002, 0.001] * 100
    res = F.simulate(losing, start=100000, years=5, sims=300)
    assert res["chance_of_loss_pct"] > 50


def test_reports_the_drawdown_to_expect_along_the_way():
    res = F.simulate([0.02, -0.02] * 100, start=100000, years=3, sims=300)
    assert res["worst_drawdown_median_pct"] < 0


def test_projection_refuses_without_enough_history():
    assert F.simulate(flat(10), start=100000)["ok"] is False


# ---------------------------------------------------------------------------
# 3) กี่ปีถึงเป้า
# ---------------------------------------------------------------------------
def test_time_to_target_is_a_range_with_a_chance_attached():
    res = F.years_to_target(flat(200, 0.002), start=100000, monthly_add=0,
                            target=200000, sims=200)
    assert res["ok"] and res["reachable"] is True
    assert res["fast_years"] <= res["median_years"] <= res["slow_years"]
    assert 0 < res["chance_pct"] <= 100
    assert "ไม่ใช่การรับประกัน" in res["note"]


def test_says_plainly_when_the_goal_is_out_of_reach():
    """เป้าไกลเกินจริงต้องบอกตรง ๆ พร้อมทางแก้ ไม่ใช่ตอบตัวเลขสวย ๆ"""
    res = F.years_to_target([0.0] * 200, start=1000, monthly_add=0,
                            target=10_000_000, sims=100, max_years=5)
    assert res["reachable"] is False
    assert "เพิ่มเงินลงทุน" in res["note"]


def test_target_already_reached_is_handled():
    res = F.years_to_target(flat(200), start=500000, monthly_add=0, target=100000)
    assert res["already_there"] is True


# ---------------------------------------------------------------------------
# 4) ต้องใช้ผลงานจริง ไม่ใช่ตัวเลขสมมติ
# ---------------------------------------------------------------------------
def test_plan_refuses_without_real_track_record(monkeypatch):
    monkeypatch.setattr(F, "real_returns",
                        lambda source="auto": {"ok": False, "error": "ยังไม่มีข้อมูล",
                                               "how_to_fix": "เปิดระบบทิ้งไว้"})
    res = F.plan(start=100000, years=10)
    assert res["ok"] is False
    assert res["how_to_fix"]


def test_plan_says_where_the_numbers_came_from(monkeypatch):
    monkeypatch.setattr(F, "real_returns",
                        lambda source="auto": {"ok": True, "source": "mt5",
                                               "label": "ผลเทรดจริงจากระบบ MT5",
                                               "returns": flat(300, 0.0004)})
    res = F.plan(start=100000, monthly_add=5000, target=1000000, years=10)
    assert res["ok"] is True
    assert res["source"] == "mt5"
    assert "MT5" in res["source_label"]
    assert res["performance"]["ok"] and res["projection"]["ok"]
    assert "to_target" in res
    assert "ไม่ใช่การรับประกัน" in res["disclaimer"]


def test_mt5_is_preferred_over_portfolio_snapshots(monkeypatch):
    """เงินจริงที่ผ่านค่าคอมและสลิปเพจแล้ว น่าเชื่อกว่ามูลค่าพอร์ตที่คำนวณเอง"""
    import services.volume_edge as VE
    monkeypatch.setattr(VE, "equity", lambda: {
        "points": [{"equity": 1000 + i} for i in range(200)]})
    got = F.real_returns("auto")
    assert got["ok"] and got["source"] == "mt5"


def test_falls_back_to_portfolio_when_mt5_is_offline(monkeypatch):
    import services.volume_edge as VE
    monkeypatch.setattr(VE, "equity", lambda: {"points": []})
    rows = [{"day": f"2026-01-{i:02d}", "value": 1000 + i} for i in range(1, 100)]
    monkeypatch.setattr("database.query", lambda *a, **k: rows)
    got = F.real_returns("auto")
    assert got["ok"] and got["source"] == "portfolio"
