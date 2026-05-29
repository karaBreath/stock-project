"""
Institutional / insider tracking — ติดตามผู้ถือหุ้นสถาบัน, นักลงทุนรายใหญ่, insider

ใช้ข้อมูลจาก yfinance:
- institutional_holders / major_holders
- insider_transactions
หมายเหตุ: ข้อมูลกระแสเงินต่างชาติรายวันของตลาดไทยไม่เปิด API ฟรี
จึงประมาณทิศทางเงินสถาบันจากปริมาณการถือครองและ insider แทน
"""
from database import cache_get, cache_set
from config import Config
from services import stock_data

try:
    import yfinance as yf
    _YF_OK = True
except Exception:
    yf = None
    _YF_OK = False


def _df_records(df, cols_map):
    if df is None or getattr(df, "empty", True):
        return []
    out = []
    for _, row in df.iterrows():
        rec = {}
        for src, dst in cols_map.items():
            if src in row:
                v = row[src]
                rec[dst] = str(v) if hasattr(v, "strftime") else (None if v != v else v)  # NaN check
        out.append(rec)
    return out


def get_ownership(ticker: str) -> dict:
    ticker = stock_data.normalize_ticker(ticker)
    cache_key = f"inst:{ticker}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    out = {"ticker": ticker, "ok": False, "institutional": [], "insider": [], "major": {}}
    if not _YF_OK:
        out["error"] = "ยังไม่ได้ติดตั้ง yfinance"
        return out

    try:
        tk = yf.Ticker(ticker)

        inst = _df_records(getattr(tk, "institutional_holders", None), {
            "Holder": "holder", "Shares": "shares", "% Out": "pct_out",
            "Value": "value", "Date Reported": "date",
        })
        out["institutional"] = inst[:15]

        insider = _df_records(getattr(tk, "insider_transactions", None), {
            "Insider": "insider", "Position": "position", "Transaction": "transaction",
            "Shares": "shares", "Value": "value", "Start Date": "date", "Text": "text",
        })
        out["insider"] = insider[:15]

        mh = getattr(tk, "major_holders", None)
        if mh is not None and not getattr(mh, "empty", True):
            try:
                out["major"] = {str(k): (None if v != v else v) for k, v in mh.iloc[:, 0].items()}
            except Exception:
                pass

        # สรุปทิศทาง insider (ซื้อ vs ขาย)
        buys = sum(1 for i in insider if "buy" in str(i.get("transaction", "")).lower() or "purchase" in str(i.get("text", "")).lower())
        sells = sum(1 for i in insider if "sale" in str(i.get("transaction", "")).lower() or "sell" in str(i.get("text", "")).lower())
        out["insider_summary"] = {"buys": buys, "sells": sells,
                                  "bias": "ซื้อสุทธิ" if buys > sells else ("ขายสุทธิ" if sells > buys else "สมดุล")}
        out["ok"] = bool(inst or insider)
    except Exception as e:
        out["error"] = str(e)

    if out.get("ok"):
        cache_set(cache_key, out, Config.FUNDAMENTAL_CACHE_TTL)
    return out
