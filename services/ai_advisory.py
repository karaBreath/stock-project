"""
AI Advisory — ถาม-ตอบเรื่องหุ้น และอธิบายเหตุผลทุกคำแนะนำ

ทำงานได้ 2 โหมด:
1) ถ้าตั้งค่า ANTHROPIC_API_KEY / OPENAI_API_KEY -> ส่งบริบท (คะแนน, อินดิเคเตอร์, ข่าว)
   ให้ LLM ช่วยอธิบาย/ตอบคำถามเชิงลึก
2) ถ้าไม่มี key -> ใช้ rule-based engine สร้างคำอธิบายจากข้อมูลวิเคราะห์จริงในระบบ

ทุกคำตอบอ้างอิงตัวเลขจริงเสมอ และมี disclaimer ว่าไม่ใช่คำแนะนำการลงทุน
"""
import re
import json

import requests

from config import Config
from database import execute
from services import scoring, stock_data


DISCLAIMER = ("\n\n⚠️ ข้อมูลนี้เพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน "
              "การลงทุนมีความเสี่ยง ผู้ลงทุนควรศึกษาข้อมูลและตัดสินใจด้วยตนเอง")


def _extract_ticker(text: str):
    """หา ticker จากคำถาม เช่น 'PTT.BK น่าซื้อไหม' หรือ 'AAPL'"""
    m = re.findall(r"\b([A-Z]{1,5}(?:\.BK)?)\b", text.upper())
    # กรองคำทั่วไป
    stop = {"AI", "RSI", "MACD", "PE", "ROE", "SET", "USD", "IPO", "ETF"}
    for c in m:
        if c not in stop:
            return c
    return None


def ask(question: str) -> dict:
    ticker = _extract_ticker(question or "")
    context = None
    if ticker:
        try:
            context = scoring.overall(ticker)
        except Exception:
            context = None

    if Config.ANTHROPIC_API_KEY:
        answer = _ask_anthropic(question, context)
    elif Config.OPENAI_API_KEY:
        answer = _ask_openai(question, context)
    else:
        answer = _rule_based(question, ticker, context)

    answer = answer + DISCLAIMER
    execute("INSERT INTO advisory_log(question, answer) VALUES(?,?)", (question, answer))
    return {"question": question, "ticker": ticker, "answer": answer,
            "context": context, "mode": _mode()}


def _mode():
    if Config.ANTHROPIC_API_KEY:
        return "anthropic"
    if Config.OPENAI_API_KEY:
        return "openai"
    return "rule-based"


def _context_text(context):
    if not context:
        return "ไม่มีข้อมูลหุ้นที่เกี่ยวข้อง"
    b = context["breakdown"]
    lines = [
        f"หุ้น: {context['name']} ({context['ticker']})",
        f"ราคา: {context['price']} {context.get('currency','')}",
        f"คะแนนรวม: {context['total_score']}/100 -> {context['recommendation']}",
        f"  • พื้นฐาน {b['fundamental']}/100, เทคนิคัล {b['technical']}/100, sentiment {b['sentiment']}/100",
    ]
    lv = context.get("levels", {})
    if lv:
        lines.append(f"จุดเข้า {lv.get('entry')} / ตัดขาดทุน {lv.get('stop_loss')} / เป้า {lv.get('target')} (R:R {lv.get('risk_reward')})")
    for n in context.get("fundamental_notes", [])[:5]:
        lines.append(f"  - {n['text']}")
    for s in context.get("technical_signals", [])[:5]:
        lines.append(f"  - {s['name']}: {s['signal']} ({s['desc']})")
    return "\n".join(lines)


def _rule_based(question, ticker, context):
    if not ticker or not context:
        return ("ผมช่วยวิเคราะห์หุ้นรายตัวได้ครับ ลองพิมพ์ชื่อหุ้นมาด้วย เช่น "
                "\"PTT.BK น่าซื้อไหม\" หรือ \"วิเคราะห์ AAPL\"\n\n"
                "ผมจะอธิบายจากคะแนนพื้นฐาน เทคนิคัล และ sentiment พร้อมจุดเข้า/ตัดขาดทุน/เป้าราคา")

    b = context["breakdown"]
    parts = [
        f"📊 สรุปการวิเคราะห์ {context['name']} ({ticker})",
        f"คะแนนรวม {context['total_score']}/100 → คำแนะนำเบื้องต้น: {context['recommendation']}",
        "",
        "เหตุผล:",
        f"• ด้านพื้นฐาน ได้ {b['fundamental']}/100",
    ]
    for n in context.get("fundamental_notes", [])[:4]:
        parts.append(f"   {'✅' if n['ok'] else '⚠️'} {n['text']}")
    parts.append(f"• ด้านเทคนิคัล ได้ {b['technical']}/100")
    for s in context.get("technical_signals", [])[:4]:
        parts.append(f"   • {s['name']}: {s['signal']} — {s['desc']}")
    parts.append(f"• ด้าน sentiment ข่าว ได้ {b['sentiment']}/100")

    lv = context.get("levels", {})
    if lv:
        parts += [
            "",
            "📌 แผนเทรด (อ้างอิง ATR/แนวรับแนวต้าน):",
            f"   จุดเข้า ~ {lv.get('entry')}",
            f"   จุดตัดขาดทุน ~ {lv.get('stop_loss')}",
            f"   เป้าราคา ~ {lv.get('target')}  (อัตราส่วนเสี่ยง:ผลตอบแทน = {lv.get('risk_reward')})",
        ]
    return "\n".join(parts)


def _ask_anthropic(question, context):
    try:
        sys = ("คุณเป็นผู้ช่วยนักวิเคราะห์หุ้นมืออาชีพ ตอบเป็นภาษาไทย กระชับ "
               "อ้างอิงตัวเลขจากบริบทที่ให้เสมอ และอธิบายเหตุผลของทุกคำแนะนำ "
               "ห้ามรับประกันผลตอบแทน")
        prompt = f"บริบทข้อมูลหุ้นจากระบบ:\n{_context_text(context)}\n\nคำถามผู้ใช้: {question}"
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": Config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-opus-4-8",
                "max_tokens": 900,
                "system": sys,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=40,
        )
        data = r.json()
        return data["content"][0]["text"]
    except Exception as e:
        return _rule_based(question, None, context) + f"\n\n(หมายเหตุ: เรียก LLM ไม่สำเร็จ: {e})"


def _ask_openai(question, context):
    try:
        prompt = (f"บริบทข้อมูลหุ้นจากระบบ:\n{_context_text(context)}\n\n"
                  f"คำถามผู้ใช้: {question}\nตอบเป็นภาษาไทย อ้างอิงตัวเลข อธิบายเหตุผล")
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {Config.OPENAI_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "คุณเป็นผู้ช่วยนักวิเคราะห์หุ้นมืออาชีพ ตอบภาษาไทย"},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 900,
            },
            timeout=40,
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return _rule_based(question, None, context) + f"\n\n(หมายเหตุ: เรียก LLM ไม่สำเร็จ: {e})"
