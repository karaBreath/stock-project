"""
ชุดทดสอบเครื่องเรียนรู้ + backtest + บทเรียนวิกฤต

รันด้วย:  python -m pytest tests/ -v
(ไม่ต้องต่อเน็ต — ใช้ข้อมูลสังเคราะห์ที่รู้คำตอบล่วงหน้าทั้งหมด)

ทำไมต้องมี
---------
ตรรกะพวกนี้ "ดูเหมือนทำงาน" ได้ง่ายมากแม้จะผิด เช่น correlation ที่จับ lag
ผิดวัน หรือ backtest ที่โกงด้วยการดูอนาคต เทสพวกนี้จึงป้อนข้อมูลที่รู้คำตอบ
อยู่แล้วเข้าไป แล้วเช็คว่าได้คำตอบนั้นกลับมาจริง
"""
import bisect
import datetime as dt
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LEARN_AUTO", "0")
os.environ.setdefault("DB_PATH", "/tmp/nebula_test.db")

from database import init_db  # noqa: E402
from services import correlation as C, news_backtest as B, crisis as X  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _db():
    if os.path.exists(os.environ["DB_PATH"]):
        os.remove(os.environ["DB_PATH"])
    init_db()
    yield


def _days(n, end=None):
    end = end or dt.date.today()
    return [(end - dt.timedelta(days=n - i)).isoformat() for i in range(n)]


# ---------------------------------------------------------------------------
# 1) การจับคู่ข่าวกับราคาต้องนับเป็น "วันทำการ"
# ---------------------------------------------------------------------------
def test_align_uses_trading_days_not_calendar_days():
    """
    ข่าวมีทุกวัน แต่ราคามีเฉพาะจันทร์-ศุกร์
    lag=3 ต้องหมายถึง 3 วันทำการเสมอ ไม่ใช่ 3 วันปฏิทิน
    (บั๊กเดิม: ข่าววันศุกร์ +3 วันปฏิทิน = จันทร์ = ห่างแค่ 1 วันทำการ)
    """
    start = dt.date(2025, 1, 6)          # จันทร์
    all_days = [(start + dt.timedelta(d)).isoformat() for d in range(40)]
    trading = [d for d in all_days if dt.date.fromisoformat(d).weekday() < 5]
    idx = {d: i for i, d in enumerate(trading)}

    rets = {d: 1.0 for d in trading}
    ser = {d: 1.0 for d in all_days}     # ข่าวมีทุกวันรวมเสาร์อาทิตย์

    for lag in (1, 2, 3, 5):
        gaps = set()
        for day in ser:
            pos = bisect.bisect_left(trading, day)
            if pos + lag < len(trading):
                gaps.add(idx[trading[pos + lag]] - idx[trading[pos]])
        assert gaps == {lag}, f"lag={lag} ได้ระยะห่างปนกัน: {sorted(gaps)}"

    xs, ys = C.align(ser, rets, 3)
    assert len(xs) == len(ys) > 20


def test_align_respects_allowed_days():
    """allowed_days ใช้จำกัดช่วง train — ห้ามหลุดไปใช้ข้อมูลนอกช่วง"""
    days = _days(40)
    rets = {d: 0.5 for d in days}
    ser = {d: 1.0 for d in days}
    train = set(days[:20])
    xs, _ = C.align(ser, rets, 1, allowed_days=train)
    assert len(xs) <= 20


# ---------------------------------------------------------------------------
# 2) เครื่องเรียนรู้ต้องจับ lag ที่ฝังไว้ได้ และไม่จับของที่ไม่มี
# ---------------------------------------------------------------------------
def test_finds_planted_lag(monkeypatch):
    """ฝังความสัมพันธ์ที่ lag=2 แล้วเครื่องต้องชี้ว่า lag=2 แรงที่สุด"""
    rng = np.random.default_rng(7)
    n = 250
    days = _days(n)
    feat = rng.normal(0, 1, n)
    noise = rng.normal(0, 1, n)
    rets = {days[j]: 0.8 * feat[j - 2] + noise[j] for j in range(2, n)}
    ser = {days[i]: float(feat[i]) for i in range(n)}

    monkeypatch.setattr(C, "_feature_series", lambda f, d: ser if f == "news:x" else {})
    monkeypatch.setattr(C, "_returns_series", lambda t, d: rets)

    res = C.analyze("T", days=n, features=["news:x"], lags=[0, 1, 2, 3, 5], save=False)
    best = max(res["links"], key=lambda L: abs(L["r"]))
    assert best["lag"] == 2
    assert best["r"] > 0.4
    assert best["n"] > n - 15, "ตัวอย่างหายไปเยอะเกินไป"


def test_bonferroni_rejects_pure_noise(monkeypatch):
    """
    ข้อมูลสุ่มล้วนที่ไม่มีความสัมพันธ์จริงเลย
    เกณฑ์หลวมจะเจอ 'ของปลอม' แต่เกณฑ์ Bonferroni ต้องไม่ปล่อยผ่าน
    """
    rng = np.random.default_rng(11)
    n = 250
    days = _days(n)
    rets = {days[i]: float(rng.normal(0, 1.4)) for i in range(n)}
    feats = {f"news:f{k}": {days[i]: float(rng.normal()) for i in range(n)}
             for k in range(16)}

    monkeypatch.setattr(C, "_feature_series", lambda f, d: feats.get(f, {}))
    monkeypatch.setattr(C, "_returns_series", lambda t, d: rets)

    res = C.analyze("NOISE", days=n, features=list(feats),
                    lags=[0, 1, 2, 3, 5], save=False)
    assert res["significant_count"] == 0, \
        f"ปล่อยของปลอมผ่าน {res['significant_count']} คู่"
    assert res["tested"] == 80


def test_critical_r_gets_stricter_with_more_tests():
    """ยิ่งทดสอบหลายคู่ เกณฑ์ต้องยิ่งเข้ม"""
    assert C._critical_r(150, 80) > C._critical_r(150, 1)
    # ข้อมูลยิ่งเยอะ เกณฑ์ยิ่งผ่อนได้
    assert C._critical_r(250, 80) < C._critical_r(120, 80)


# ---------------------------------------------------------------------------
# 3) catalyst — ปรับคะแนนเฉพาะความสัมพันธ์ที่ผ่านเกณฑ์
# ---------------------------------------------------------------------------
def test_catalyst_zero_when_nothing_learned():
    """ยังไม่เคยเรียนรู้หุ้นตัวนี้ -> ห้ามแตะคะแนน"""
    c = C.catalyst_signal("NEVER_SEEN.BK")
    assert c["ok"] is False
    assert c["adjust"] == 0


def test_catalyst_filters_weak_and_lag_zero(monkeypatch):
    """
    ต้องใช้เฉพาะความสัมพันธ์ที่ n พอ + |r| พอ + |t| พอ + lag>=1
    lag=0 ใช้ทำนายอนาคตไม่ได้ ต้องถูกคัดทิ้งแม้ r จะสูงมาก
    """
    C._save_link("FILT.BK", "news:energy", 2, 0.42, 150, 5.2, 64.0, 180)   # ผ่าน
    C._save_link("FILT.BK", "news:tech", 1, 0.42, 150, 1.5, 64.0, 180)     # t ต่ำ
    C._save_link("FILT.BK", "news:market", 0, 0.90, 150, 9.9, 70.0, 180)   # lag=0
    C._save_link("FILT.BK", "news:trade", 2, 0.60, 12, 2.1, 66.0, 180)     # n น้อย

    monkeypatch.setattr(
        "services.gdelt.theme_signals",
        lambda timespan="7d": {"rows": [
            {"key": k, "deviation": 1.5, "tone": 1.0, "label": k}
            for k in ("energy", "tech", "market", "trade")]})

    c = C.catalyst_signal("FILT.BK")
    assert c["used"] == 1, f"ควรใช้แค่ 1 คู่ แต่ใช้ {c['used']}"
    assert c["adjust"] > 0


def test_catalyst_adjust_is_capped(monkeypatch):
    """แม้สัญญาณสุดขีดก็ห้ามปรับเกิน ±10 คะแนน"""
    C._save_link("CAP.BK", "news:energy", 2, 0.95, 300, 20.0, 80.0, 180)
    monkeypatch.setattr(
        "services.gdelt.theme_signals",
        lambda timespan="7d": {"rows": [
            {"key": "energy", "deviation": 999, "tone": 9, "label": "x"}]})
    c = C.catalyst_signal("CAP.BK")
    assert abs(c["adjust"]) <= C.CATALYST_MAX_ADJUST


# ---------------------------------------------------------------------------
# 4) backtest — ต้องจับ overfitting ได้ ไม่หลอกตัวเอง
# ---------------------------------------------------------------------------
def _bt_setup(monkeypatch, mode):
    """สร้างข้อมูล: สัญญาณจริงที่ lag=2 ซึ่ง 'อยู่ยาว' หรือ 'หายไปหลัง train'"""
    rng = np.random.default_rng(9)
    n = 500
    days = _days(n)
    split = int(n * 0.6)
    sig = {days[i]: float(rng.normal()) for i in range(n)}
    rets = {}
    for i in range(n - 2):
        faded = mode == "fades" and i >= split
        rets[days[i + 2]] = (float(rng.normal(0.02, 1.4)) if faded
                             else 1.1 * sig[days[i]] + float(rng.normal(0, 1.1)))
    feats = {f"news:f{k}": {days[i]: float(rng.normal()) for i in range(n)}
             for k in range(15)}
    feats["news:real"] = sig
    monkeypatch.setattr(C, "_feature_series", lambda f, d: feats.get(f, {}))
    monkeypatch.setattr(C, "_returns_series", lambda t, d: rets)
    monkeypatch.setattr(C, "default_features", lambda t="": list(feats))
    return n


def _noise_backtest(monkeypatch, seed, n=400):
    rng = np.random.default_rng(seed)
    days = _days(n)
    rets = {days[i]: float(rng.normal(0.02, 1.4)) for i in range(n)}
    feats = {f"news:f{k}": {days[i]: float(rng.normal()) for i in range(n)}
             for k in range(16)}
    monkeypatch.setattr(C, "_feature_series", lambda f, d: feats.get(f, {}))
    monkeypatch.setattr(C, "_returns_series", lambda t, d: rets)
    monkeypatch.setattr(C, "default_features", lambda t="": list(feats))
    return B.run("NOISE", days=n)


def test_backtest_rarely_finds_signal_in_pure_noise(monkeypatch):
    """
    ข้อมูลสุ่มล้วน 12 ชุด

    หมายเหตุสำคัญ: Bonferroni ไม่ได้การันตีว่าจะเจอ 0 คู่เสมอ — มันคุม
    โอกาสเจอ "ของปลอมอย่างน้อย 1 คู่" ไว้ที่ราว 5% ต่อการทดสอบ 1 ชุด
    เทสนี้จึงวัดว่า *อัตรา* ต่ำจริง ไม่ใช่บังคับให้เป็นศูนย์
    """
    found = sum(1 for s in range(12)
                if _noise_backtest(monkeypatch, s)["passing_count"] > 0)
    assert found <= 3, f"เจอสัญญาณลวงใน {found}/12 ชุด — เกณฑ์หลวมเกินไป"


def test_backtest_never_recommends_trading_pure_noise(monkeypatch):
    """
    สิ่งที่ต้องรับประกันจริง ๆ: ต่อให้เผลอเจอสัญญาณลวงในช่วง train
    ผลนอกกลุ่มตัวอย่างต้องไม่ออกมาเป็น 'ดี ควรเทรดตาม'
    """
    for seed in range(12):
        r = _noise_backtest(monkeypatch, seed)
        assert r["ok"]
        assert r["verdict"]["level"] != "good", \
            f"seed {seed}: แนะนำให้เทรดตามสัญญาณลวง — {r['verdict']['text']}"


def test_backtest_flags_signal_that_stopped_working(monkeypatch):
    """สัญญาณที่เคยจริงแต่หายไป -> ต้องขึ้นคำเตือน overfit"""
    n = _bt_setup(monkeypatch, "fades")
    r = B.run("FADE", days=n)
    assert r["signal"] is not None
    assert r["verdict"]["level"] == "overfit", \
        f"ไม่จับ overfit: {r['verdict']}"
    assert "อย่าเอาไปใช้ตัดสินใจ" in r["verdict"]["text"]


def test_backtest_passes_persistent_signal(monkeypatch):
    """สัญญาณจริงที่อยู่ยาว -> ต้องไม่ถูกตีตก"""
    n = _bt_setup(monkeypatch, "persists")
    r = B.run("REAL", days=n)
    assert r["signal"]["feature"] == "news:real"
    assert r["signal"]["lag"] == 2
    assert r["verdict"]["level"] in ("good", "weak")


def test_backtest_train_and_test_do_not_overlap(monkeypatch):
    """ช่วงเรียนรู้กับช่วงทดสอบต้องไม่ทับกัน (กันโกงด้วยการดูอนาคต)"""
    n = _bt_setup(monkeypatch, "persists")
    r = B.run("REAL", days=n)
    assert r["train"]["to"] < r["test"]["from"]
    assert r["train"]["days"] > 0 and r["test"]["days"] > 0


# ---------------------------------------------------------------------------
# 5) บทเรียนวิกฤต — วัดความเสียหายและเวลาฟื้นให้ถูก
# ---------------------------------------------------------------------------
@pytest.fixture
def synthetic_gfc(monkeypatch):
    """ราคาที่ร่วง 50% ช่วงซับไพรม์ แล้วฟื้นกลับพอดี 3 ปีหลังเริ่มร่วง"""
    gs, gt = dt.date(2007, 10, 9), dt.date(2009, 3, 9)
    rec = dt.date(2010, 10, 9)
    px, d = {}, dt.date(2005, 1, 1)
    while d < dt.date(2013, 1, 1):
        if d < gs:
            v = 100.0
        elif d <= gt:
            v = 100 - 50 * ((d - gs).days / (gt - gs).days)
        elif d < rec:
            v = 50 + 50 * ((d - gt).days / (rec - gt).days)
        else:
            v = 100.0 + (d - rec).days * 0.01
        px[d.isoformat()] = v
        d += dt.timedelta(days=1)
    monkeypatch.setattr(X, "_closes", lambda sym: px)
    return px


def test_crisis_measures_drawdown_and_recovery(synthetic_gfc):
    r = X.impact("TEST")
    gfc = next(c for c in r["crises"] if c["key"] == "gfc")
    assert -50.5 < gfc["drawdown_pct"] < -49.5
    assert 1090 < gfc["recovery_days"] < 1100      # ~3 ปี


def test_crisis_marks_uncovered_when_data_ends_early(synthetic_gfc):
    """
    ข้อมูลจบปี 2012 -> วิกฤตปี 2020/2022 ต้องถูกทำเครื่องหมายว่าไม่ครอบคลุม
    และ covered_count ต้องตรงกับจำนวนที่วัดได้จริง
    """
    r = X.impact("TEST")
    covered = [c for c in r["crises"] if c["covered"]]
    assert r["covered_count"] == len(covered)
    covid = next(c for c in r["crises"] if c["key"] == "covid")
    assert covid["covered"] is False
    assert covid["note_extra"]


def test_crisis_never_reports_drawdown_without_data(synthetic_gfc):
    """ทุกแถวที่บอกว่า covered ต้องมีตัวเลข drawdown จริง"""
    r = X.impact("TEST")
    for c in r["crises"]:
        if c["covered"]:
            assert c["drawdown_pct"] is not None
