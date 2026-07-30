"""
แผนอิสรภาพ — เครื่องคำนวณทบต้นที่ยึด "ผลงานจริง" ไม่ใช่ตัวเลขที่อยากให้เป็น

ทำไมเครื่องคำนวณทบต้นทั่วไปหลอกคน
----------------------------------
ส่วนใหญ่ให้กรอก "ผลตอบแทนต่อปี" เองแล้วคูณทบไปเรื่อย ๆ ปัญหาคือ
  1. คนกรอกตัวเลขที่อยากได้ ไม่ใช่ตัวเลขที่ตัวเองทำได้จริง
  2. ผลตอบแทนจริงไม่คงที่ ปีดีปีร้ายสลับกัน การคูณค่าเฉลี่ยตรง ๆ
     ให้ผลสูงเกินจริงเสมอ (ค่าเฉลี่ยเลขคณิต > ค่าเฉลี่ยเรขาคณิต)
  3. ไม่บอกว่าระหว่างทางจะเจอขาดทุนหนักแค่ไหน ซึ่งเป็นตัวที่ทำให้คนเลิกกลางคัน

เครื่องนี้จึงทำต่างออกไป
  - ดึง "ผลตอบแทนรายวันจริง" จากพอร์ตที่บันทึกไว้ หรือจากผลเทรด MT5 จริง
  - ใช้ค่าเฉลี่ยเรขาคณิต (CAGR) ซึ่งเป็นอัตราทบต้นที่เกิดขึ้นจริง
  - จำลองอนาคตแบบสุ่มลำดับผลตอบแทนจริง (bootstrap) หลายพันรอบ
    แล้วรายงานเป็น "ช่วง" ไม่ใช่ตัวเลขเดียว เพราะอนาคตไม่ใช่เส้นตรง
  - รายงานขาดทุนสูงสุดที่เจอในการจำลอง เพื่อให้เห็นว่าต้องทนอะไรบ้าง

⚠️ นี่คือการประมาณจากอดีต ไม่ใช่การรับประกัน ผลงานในอดีตไม่การันตีอนาคต
"""
import datetime as dt
import math
import random

TRADING_DAYS = 252
DEFAULT_SIMS = 2000
MIN_SAMPLES = 60           # ผลตอบแทนรายวันน้อยกว่านี้ ประมาณอะไรไม่ได้จริง
MAX_YEARS = 50


# ---------------------------------------------------------------------------
# สถิติจากผลงานจริง
# ---------------------------------------------------------------------------
def stats_from_returns(daily) -> dict:
    """
    สรุปผลงานจริงจากผลตอบแทนรายวัน (หน่วยเป็นสัดส่วน เช่น 0.01 = +1%)

    ใช้ CAGR (ค่าเฉลี่ยเรขาคณิต) ไม่ใช่ค่าเฉลี่ยธรรมดา
    เพราะกำไร 50% แล้วขาดทุน 50% ไม่ได้เท่าทุน แต่เหลือ 75%
    ค่าเฉลี่ยธรรมดาจะบอกว่า 0% ซึ่งผิดจากความจริงที่ -25%
    """
    rets = [float(r) for r in daily if r is not None and r == r]
    n = len(rets)
    if n < MIN_SAMPLES:
        return {"ok": False,
                "error": f"มีผลตอบแทนรายวันแค่ {n} วัน (ต้องการ {MIN_SAMPLES}+) "
                         "— เก็บสถิติให้นานกว่านี้ก่อนค่อยวางแผนระยะยาว",
                "samples": n}

    growth = 1.0
    for r in rets:
        growth *= (1 + r)
    if growth <= 0:
        return {"ok": False, "samples": n,
                "error": "ผลตอบแทนสะสมติดลบจนหมดพอร์ต — วางแผนทบต้นต่อไม่ได้"}

    years = n / TRADING_DAYS
    cagr = growth ** (1 / years) - 1 if years > 0 else 0.0
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1)
    vol_annual = math.sqrt(var) * math.sqrt(TRADING_DAYS)

    peak = equity = 1.0
    max_dd = 0.0
    for r in rets:
        equity *= (1 + r)
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1)

    wins = sum(1 for r in rets if r > 0)
    return {
        "ok": True,
        "samples": n,
        "years": round(years, 2),
        "total_return_pct": round((growth - 1) * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "vol_annual_pct": round(vol_annual * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "win_rate_pct": round(wins / n * 100, 1),
        # Sharpe อย่างง่าย (ไม่หักดอกเบี้ยปลอดความเสี่ยง) ใช้เทียบกันเองเท่านั้น
        "sharpe": round((mean * TRADING_DAYS) / (vol_annual or 1e-9), 2),
    }


# ---------------------------------------------------------------------------
# จำลองอนาคต
# ---------------------------------------------------------------------------
def _percentile(sorted_vals, p: float):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


def simulate(daily, start: float, monthly_add: float = 0.0,
             years: int = 10, sims: int = DEFAULT_SIMS, seed: int = 42) -> dict:
    """
    สุ่มลำดับผลตอบแทนจริงใหม่หลายพันรอบ (bootstrap) แล้วดูการกระจายของผลลัพธ์

    ทำไมต้องสุ่มลำดับใหม่: ถ้าเอาผลตอบแทนอดีตมาเรียงเดิมซ้ำ จะได้คำตอบเดียว
    ซึ่งให้ความมั่นใจผิด ๆ การสุ่มลำดับใหม่ทำให้เห็นว่า "ลำดับของกำไรขาดทุน"
    ส่งผลต่อปลายทางมากแค่ไหน โดยยังใช้ตัวผลตอบแทนจริงของเราเองทั้งหมด

    ใช้ seed คงที่เพื่อให้ผลลัพธ์เดิมทุกครั้ง — ตัวเลขที่เต้นทุกครั้งที่รีเฟรช
    ทำให้ตัดสินใจไม่ได้และดูเหมือนระบบมั่ว
    """
    rets = [float(r) for r in daily if r is not None and r == r]
    if len(rets) < MIN_SAMPLES:
        return {"ok": False,
                "error": f"ข้อมูลไม่พอ (มี {len(rets)} วัน ต้องการ {MIN_SAMPLES}+)"}

    years = max(1, min(MAX_YEARS, int(years)))
    sims = max(200, min(5000, int(sims)))
    days = years * TRADING_DAYS
    daily_add = (monthly_add * 12) / TRADING_DAYS if monthly_add else 0.0

    rng = random.Random(seed)
    finals, worst_dds = [], []
    for _ in range(sims):
        equity = float(start)
        peak, dd = equity, 0.0
        for _ in range(days):
            equity = equity * (1 + rets[rng.randrange(len(rets))]) + daily_add
            if equity <= 0:
                equity = 0.0
                break
            peak = max(peak, equity)
            dd = min(dd, equity / peak - 1)
        finals.append(equity)
        worst_dds.append(dd)

    finals.sort()
    worst_dds.sort()
    invested = start + monthly_add * 12 * years
    median = _percentile(finals, 0.5)
    return {
        "ok": True,
        "years": years,
        "sims": sims,
        "start": start,
        "monthly_add": monthly_add,
        "invested_total": round(invested, 2),
        "p10": round(_percentile(finals, 0.10), 2),
        "p25": round(_percentile(finals, 0.25), 2),
        "median": round(median, 2),
        "p75": round(_percentile(finals, 0.75), 2),
        "p90": round(_percentile(finals, 0.90), 2),
        "median_multiple": round(median / invested, 2) if invested else None,
        "worst_drawdown_median_pct": round(_percentile(worst_dds, 0.5) * 100, 1),
        "worst_drawdown_p10_pct": round(_percentile(worst_dds, 0.10) * 100, 1),
        "chance_of_loss_pct": round(
            sum(1 for f in finals if f < invested) / len(finals) * 100, 1),
    }


def years_to_target(daily, start: float, monthly_add: float, target: float,
                    sims: int = 600, max_years: int = MAX_YEARS,
                    seed: int = 42) -> dict:
    """
    ต้องใช้กี่ปีถึงจะถึงเป้า — ตอบเป็นช่วง ไม่ใช่ตัวเลขเดียว

    รายงาน 3 เส้น: โชคดี (เร็วสุด 25%) · กลาง ๆ (50%) · โชคร้าย (ช้าสุด 25%)
    เพราะการบอกปีเดียวคือการสัญญาในสิ่งที่ไม่มีใครรู้
    """
    rets = [float(r) for r in daily if r is not None and r == r]
    if len(rets) < MIN_SAMPLES:
        return {"ok": False,
                "error": f"ข้อมูลไม่พอ (มี {len(rets)} วัน ต้องการ {MIN_SAMPLES}+)"}
    if target <= start:
        return {"ok": True, "already_there": True, "median_years": 0}

    rng = random.Random(seed)
    daily_add = (monthly_add * 12) / TRADING_DAYS if monthly_add else 0.0
    limit = max_years * TRADING_DAYS
    reached = []
    never = 0
    for _ in range(sims):
        equity = float(start)
        for d in range(1, limit + 1):
            equity = equity * (1 + rets[rng.randrange(len(rets))]) + daily_add
            if equity >= target:
                reached.append(d / TRADING_DAYS)
                break
            if equity <= 0:
                break
        else:
            never += 1
            continue
        if equity < target:
            never += 1

    reached.sort()
    if not reached:
        return {"ok": True, "reachable": False, "sims": sims,
                "note": f"จำลอง {sims} รอบแล้วไม่ถึงเป้าเลยภายใน {max_years} ปี "
                        "— ต้องเพิ่มเงินลงทุนต่อเดือน หรือปรับเป้าให้เป็นจริงกว่านี้"}
    return {
        "ok": True,
        "reachable": True,
        "sims": sims,
        "target": target,
        "fast_years": round(_percentile(reached, 0.25), 1),
        "median_years": round(_percentile(reached, 0.50), 1),
        "slow_years": round(_percentile(reached, 0.75), 1),
        "chance_pct": round(len(reached) / sims * 100, 1),
        "note": ("ตัวเลขนี้มาจากการสุ่มลำดับผลตอบแทนจริงของคุณเอง "
                 "ไม่ใช่การรับประกัน — ผลงานอดีตไม่การันตีอนาคต"),
    }


# ---------------------------------------------------------------------------
# ดึงผลตอบแทนจริงจากแหล่งที่มีอยู่
# ---------------------------------------------------------------------------
def _returns_from_equity(points) -> list:
    """แปลงเส้น equity เป็นผลตอบแทนรายวัน"""
    vals = [float(p) for p in points if p is not None and float(p) > 0]
    return [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals))]


def real_returns(source: str = "auto") -> dict:
    """
    หาผลตอบแทนรายวันจริงจากแหล่งที่ดีที่สุดที่มี

    ลำดับความน่าเชื่อถือ:
      1. equity จริงจากระบบเทรด MT5 (เงินจริง ผ่านค่าคอมและสลิปเพจแล้ว)
      2. มูลค่าพอร์ตที่ระบบเก็บ snapshot ไว้ทุกชั่วโมง
    ถ้าไม่มีทั้งคู่ ต้องบอกตรง ๆ ว่ายังวางแผนไม่ได้ ไม่ใช่ยัดตัวเลขสมมติให้
    """
    tried = []

    if source in ("auto", "mt5"):
        try:
            from services import volume_edge
            eq = volume_edge.equity()
            pts = [p.get("equity") for p in (eq.get("points") or eq.get("equity") or [])
                   if isinstance(p, dict)]
            rets = _returns_from_equity(pts)
            if len(rets) >= MIN_SAMPLES:
                return {"ok": True, "source": "mt5", "returns": rets,
                        "label": "ผลเทรดจริงจากระบบ MT5"}
            tried.append(f"MT5: มี {len(rets)} วัน")
        except Exception as e:
            tried.append(f"MT5: {str(e)[:60]}")

    if source in ("auto", "portfolio"):
        try:
            from database import query
            rows = query(
                "SELECT day, value FROM observations "
                "WHERE kind = 'portfolio' AND key = 'total_value' ORDER BY day") or []
            rets = _returns_from_equity([r["value"] for r in rows])
            if len(rets) >= MIN_SAMPLES:
                return {"ok": True, "source": "portfolio", "returns": rets,
                        "label": "มูลค่าพอร์ตที่ระบบเก็บไว้"}
            tried.append(f"พอร์ต: มี {len(rets)} วัน")
        except Exception as e:
            tried.append(f"พอร์ต: {str(e)[:60]}")

    return {
        "ok": False, "returns": [],
        "error": "ยังไม่มีผลงานจริงมากพอให้วางแผน (" + " · ".join(tried) + ")",
        "how_to_fix": (f"ต้องมีผลตอบแทนรายวันอย่างน้อย {MIN_SAMPLES} วัน "
                       "— เปิดระบบทิ้งไว้ให้เก็บสถิติต่อ หรือเชื่อมพอร์ต MT5 "
                       "เพื่อใช้ผลเทรดจริง"),
    }


def plan(start: float = 0.0, monthly_add: float = 0.0, target: float = 0.0,
         years: int = 10, source: str = "auto") -> dict:
    """รวมทุกอย่างเป็นแผนเดียว — ใช้จากหน้าเว็บ"""
    data = real_returns(source)
    if not data.get("ok"):
        return {"ok": False, "error": data["error"],
                "how_to_fix": data.get("how_to_fix")}

    rets = data["returns"]
    out = {
        "ok": True,
        "source": data["source"],
        "source_label": data["label"],
        "performance": stats_from_returns(rets),
        "projection": simulate(rets, start, monthly_add, years),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "disclaimer": ("ประมาณจากผลงานจริงในอดีตของคุณเอง โดยสุ่มลำดับใหม่หลายพันรอบ "
                       "ไม่ใช่การรับประกันผลตอบแทน และไม่ใช่คำแนะนำการลงทุน"),
    }
    if target and target > 0:
        out["to_target"] = years_to_target(rets, start, monthly_add, target)
    return out
