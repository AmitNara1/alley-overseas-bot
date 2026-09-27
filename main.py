"""
Alley Overseas — WhatsApp Lead-Gen Chatbot v2.0
================================================
Stack : FastAPI + Gupshup WhatsApp API + Google Sheets
Deploy: Railway (always-on, free tier)
Author: Built with Antigravity AI
"""

import asyncio
import csv
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv()

# Configure logger to stdout (fixes red error bars on Railway)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("alley-bot")

# ─────────────────────────────────────────────────────────────────────────────
# ENVIRONMENT CONFIG
# ─────────────────────────────────────────────────────────────────────────────

GUPSHUP_API_KEY    = os.getenv("GUPSHUP_API_KEY", "")
GUPSHUP_APP_NAME   = os.getenv("GUPSHUP_APP_NAME", "AlleyOverseas")
GUPSHUP_SOURCE     = os.getenv("GUPSHUP_SOURCE", "")   # Your WA number, no + or spaces, e.g. 919876543210
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_CREDS_JSON  = os.getenv("GOOGLE_CREDS_JSON", "")  # Full service-account JSON as a string

# ─────────────────────────────────────────────────────────────────────────────
# PERSISTENT HTTP CLIENT POOL (ULTRA-FAST GUPSHUP DISPATCH)
# ─────────────────────────────────────────────────────────────────────────────

http_client: httpx.AsyncClient | None = None

def get_http_client() -> httpx.AsyncClient:
    global http_client
    if http_client is None or http_client.is_closed:
        http_client = httpx.AsyncClient(
            timeout=8.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
    return http_client


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE SHEETS HELPER (gracefully optional)
# ─────────────────────────────────────────────────────────────────────────────

_gc = None   # gspread client (initialised lazily)

def _get_sheets_client():
    """Return a gspread client, or None if credentials are missing."""
    global _gc
    if _gc:
        return _gc
    if not GOOGLE_SHEET_ID or not GOOGLE_CREDS_JSON:
        return None
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        creds_dict = json.loads(GOOGLE_CREDS_JSON)
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=[
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        _gc = gspread.authorize(creds)
        log.info("Google Sheets client initialised ✅")
    except Exception as exc:
        log.warning("Google Sheets unavailable: %s", exc)
        _gc = None
    return _gc


def append_to_sheet(row: list) -> None:
    """Append one row to the Google Sheet (silently skips if Sheets not configured)."""
    gc = _get_sheets_client()
    if not gc:
        return
    try:
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        ws = sh.sheet1
        # Add header row if the sheet is empty
        if ws.row_count == 0 or not ws.get_all_values():
            ws.append_row(
                ["Timestamp", "Phone", "Status", "Name", "Country", "Study Level", "Intake", "Budget"],
                value_input_option="RAW",
            )
        ws.append_row(row, value_input_option="RAW")
        log.info("Lead appended to Google Sheet ✅")
    except Exception as exc:
        log.error("Failed to append to Sheet: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# CSV STORAGE & REAL-TIME AUTOSAVE
# ─────────────────────────────────────────────────────────────────────────────

LEADS_FILE = "leads.csv"
CSV_HEADERS = [
    "timestamp", "phone", "status", "name", "country", "study_level", "intake", "budget",
]


def save_lead_csv(phone: str, data: dict, status: str = "Completed") -> None:
    """Save or update lead entry in CSV."""
    rows = []
    found = False
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if os.path.isfile(LEADS_FILE):
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                # Update existing row if from same phone session
                if r.get("phone") == phone and r.get("status") != "Completed":
                    r["timestamp"] = now_str
                    r["status"] = status
                    for k in CSV_HEADERS[3:]:
                        if k in data:
                            r[k] = data[k]
                    found = True
                rows.append(r)

    if not found:
        new_row = {
            "timestamp": now_str,
            "phone": phone,
            "status": status,
        }
        for k in CSV_HEADERS[3:]:
            new_row[k] = data.get(k, "")
        rows.append(new_row)

    with open(LEADS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    log.info("Lead saved to leads.csv [%s] ✅", status)


def save_lead(phone: str, data: dict, status: str = "Completed") -> None:
    """Save to CSV (always) and Google Sheets (if configured)."""
    save_lead_csv(phone, data, status)
    sheet_row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        phone,
        status,
        data.get("name", ""),
        data.get("country", ""),
        data.get("study_level", ""),
        data.get("intake", ""),
        data.get("budget", ""),
    ]
    append_to_sheet(sheet_row)


# ─────────────────────────────────────────────────────────────────────────────
# GUPSHUP OUTBOUND MESSAGING
# ─────────────────────────────────────────────────────────────────────────────

GUPSHUP_API_URL = "https://api.gupshup.io/wa/api/v1/msg"


async def send_message(destination: str, text: str) -> None:
    """
    Send a WhatsApp text message via Gupshup using pooled persistent HTTP connection.
    destination: user's phone number (e.g. 919876543210, no +)
    """
    if not GUPSHUP_API_KEY or not GUPSHUP_SOURCE:
        log.warning("Gupshup credentials not configured — message not sent.")
        return

    payload = {
        "channel": "whatsapp",
        "source": GUPSHUP_SOURCE,
        "destination": destination,
        "message": json.dumps({"type": "text", "text": text}),
        "src.name": GUPSHUP_APP_NAME,
    }
    headers = {"apikey": GUPSHUP_API_KEY, "Content-Type": "application/x-www-form-urlencoded"}

    try:
        client = get_http_client()
        resp = await client.post(GUPSHUP_API_URL, data=payload, headers=headers)
        if resp.status_code == 202:
            log.info("Message sent to %s ✅", destination)
        else:
            log.warning("Gupshup returned %s: %s", resp.status_code, resp.text)
    except Exception as exc:
        log.error("Failed to send message: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATION FLOW DEFINITION (4 HIGH-CONVERSION QUESTIONS)
# ─────────────────────────────────────────────────────────────────────────────

FLOW = [
    {
        "state": "q1_country",
        "question": (
            "🌍 *Question 1 of 4*\n"
            "Which country are you interested in?\n\n"
            "1️⃣ 🇬🇧 UK\n"
            "2️⃣ 🇺🇸 USA\n"
            "3️⃣ 🇨🇦 Canada\n"
            "4️⃣ 🇦🇺 Australia\n"
            "5️⃣ 🇮🇪 Ireland\n"
            "6️⃣ 🇦🇪 UAE\n"
            "7️⃣ 🇫🇷 France\n"
            "8️⃣ 🌍 Not Sure Yet\n\n"
            "_Reply with a number (1–8)_"
        ),
        "options": ["UK 🇬🇧", "USA 🇺🇸", "Canada 🇨🇦", "Australia 🇦🇺", "Ireland 🇮🇪", "UAE 🇦🇪", "France 🇫🇷", "Not Sure Yet"],
        "field": "country",
        "max": 8,
    },
    {
        "state": "q2_level",
        "question": (
            "📚 *Question 2 of 4*\n"
            "What are you planning to study?\n\n"
            "1️⃣ Bachelor's\n"
            "2️⃣ Master's\n"
            "3️⃣ MBA\n"
            "4️⃣ Not Sure\n\n"
            "_Reply with a number (1–4)_"
        ),
        "options": ["Bachelor's", "Master's", "MBA", "Not Sure"],
        "field": "study_level",
        "max": 4,
    },
    {
        "state": "q3_intake",
        "question": (
            "📅 *Question 3 of 4*\n"
            "When do you plan to start?\n\n"
            "1️⃣ Jan Intake\n"
            "2️⃣ May Intake\n"
            "3️⃣ Sept Intake\n"
            "4️⃣ Next Year\n"
            "5️⃣ Just Exploring\n\n"
            "_Reply with a number (1–5)_"
        ),
        "options": ["Jan Intake", "May Intake", "Sept Intake", "Next Year", "Just Exploring"],
        "field": "intake",
        "max": 5,
    },
    {
        "state": "q4_budget",
        "question": (
            "💰 *Question 4 of 4*\n"
            "What is your approximate budget?\n\n"
            "1️⃣ Under ₹15 Lakhs\n"
            "2️⃣ ₹15–25 Lakhs\n"
            "3️⃣ ₹25–40 Lakhs\n"
            "4️⃣ ₹40 Lakhs+\n"
            "5️⃣ Need Education Loan\n\n"
            "_Reply with a number (1–5)_"
        ),
        "options": ["Under ₹15 Lakhs", "₹15–25 Lakhs", "₹25–40 Lakhs", "₹40 Lakhs+", "Need Education Loan"],
        "field": "budget",
        "max": 5,
    },
]

FLOW_STATE_MAP: dict[str, int] = {q["state"]: i for i, q in enumerate(FLOW)}



# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

WELCOME_MESSAGE = """\
👋 Hi! Welcome to *Alley Overseas*! 🌟

I'm your virtual study abroad assistant.

I'll help you:
✅ Find the right university
✅ Estimate your admission chances
✅ Connect you with a counsellor

It takes less than *30 seconds* (just 4 quick questions!). Let's get started! 🚀
━━━━━━━━━━━━━━━━━━━━━━"""

THANK_YOU = """\
🎉 *Thank You!*

Your preferences have been received. ✅

One of our study abroad experts will contact you on WhatsApp/Phone *shortly*.

━━━━━━━━━━━━━━━━━━━━━━
Need immediate assistance?

📞 Reply *CALL* → Request an instant call back
💬 Reply *AGENT* → Chat with a counsellor
━━━━━━━━━━━━━━━━━━━━━━
_Alley Overseas — Your Gateway to Global Education_ 🌍"""

CALL_MSG = """\
📞 *Call Back Requested!*

Our team will call you within *2 working hours*.
🕒 Mon–Sat, 9AM–6PM IST

_We look forward to speaking with you!_ 😊"""

AGENT_MSG = """\
💬 *Connecting you with a Counsellor...*

A team member will reach out on WhatsApp *shortly*!
🕒 Mon–Sat, 9AM–6PM IST

_We're here to help you every step of the way!_ 🚀"""

ALREADY_DONE_MSG = """\
🎉 You've already submitted your study preferences!

Our team will contact you soon.

📞 Reply *CALL* to request a call back
💬 Reply *AGENT* to chat with a counsellor

_Type *restart* to start a fresh assessment._"""

ABANDONED_REENGAGE_MSG = """\
⏳ *We've saved your progress!*

We noticed you paused before finishing. Our study abroad team at *Alley Overseas* has saved your preferences so far and a counsellor will be happy to assist you!

━━━━━━━━━━━━━━━━━━━━━━
🔄 Reply *restart* anytime to begin a fresh application
📞 Reply *CALL* to request an instant call back
━━━━━━━━━━━━━━━━━━━━━━
_Alley Overseas — Your Gateway to Global Education_ 🌍"""


# ─────────────────────────────────────────────────────────────────────────────
# IN-MEMORY SESSIONS & INACTIVITY TIMEOUT ENGINE
# ─────────────────────────────────────────────────────────────────────────────

sessions: dict[str, dict] = {}
inactivity_timers: dict[str, asyncio.Task] = {}
INACTIVITY_TIMEOUT_SECONDS = int(os.getenv("INACTIVITY_TIMEOUT_SECONDS", "300"))  # 5 mins default


def get_session(phone: str) -> dict:
    if phone not in sessions:
        sessions[phone] = {"state": "start", "step_index": -1, "data": {}}
    return sessions[phone]


def reset_session(phone: str) -> dict:
    cancel_inactivity_timer(phone)
    sessions[phone] = {"state": "start", "step_index": -1, "data": {}}
    return sessions[phone]


def cancel_inactivity_timer(phone: str) -> None:
    if phone in inactivity_timers:
        task = inactivity_timers.pop(phone)
        if not task.done():
            task.cancel()


def start_inactivity_timer(phone: str) -> None:
    cancel_inactivity_timer(phone)
    task = asyncio.create_task(_inactivity_timeout_handler(phone))
    inactivity_timers[phone] = task


async def _inactivity_timeout_handler(phone: str) -> None:
    try:
        await asyncio.sleep(INACTIVITY_TIMEOUT_SECONDS)
        session = get_session(phone)
        st = session.get("state", "")
        if st not in ("start", "complete"):
            # Mark lead as Abandoned / Partial in CSV / Sheets
            step_name = st.replace("q", "Question ")
            save_lead(phone, session["data"], status=f"Abandoned ({step_name})")
            session["state"] = "complete"
            await send_message(phone, ABANDONED_REENGAGE_MSG)
            log.info("Sent abandoned re-engagement message to %s [%s] ✅", phone, step_name)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        log.error("Error in inactivity timer for %s: %s", phone, exc)


# ─────────────────────────────────────────────────────────────────────────────
# CORE MESSAGE HANDLER
# ─────────────────────────────────────────────────────────────────────────────

async def handle_message(phone: str, raw_text: str, sender_name: str = "") -> None:
    """Process an incoming WhatsApp message and send the appropriate reply."""
    cancel_inactivity_timer(phone)

    body     = raw_text.strip()
    body_low = body.lower()
    session  = get_session(phone)

    if sender_name and not session["data"].get("name"):
        session["data"]["name"] = sender_name

    # ── Global special commands ────────────────────────────────────────────
    if body_low == "call":
        await send_message(phone, CALL_MSG)
        return

    if body_low in ("agent", "whatsapp"):
        await send_message(phone, AGENT_MSG)
        return

    # ── Reset triggers ─────────────────────────────────────────────────────
    if body_low in ("hi", "hello", "hey", "start", "restart", "menu", "begin", "reset"):
        session = reset_session(phone)
        if sender_name:
            session["data"]["name"] = sender_name

    state = session["state"]

    # ── START → show welcome + Q1 ──────────────────────────────────────────
    if state == "start":
        session["state"] = "q1_country"
        session["step_index"] = 0
        save_lead(phone, session["data"], status="In Progress (Q1)")
        start_inactivity_timer(phone)
        await send_message(phone, WELCOME_MESSAGE + "\n\n" + FLOW[0]["question"])
        return

    # ── Q1–Q4 numbered-choice questions ───────────────────────────────────
    if state in FLOW_STATE_MAP:
        idx = session["step_index"]
        q   = FLOW[idx]

        try:
            choice = int(body)
        except ValueError:
            start_inactivity_timer(phone)
            await send_message(
                phone,
                f"⚠️ Please reply with a *number* between 1 and {q['max']}.\n\n{q['question']}"
            )
            return

        if not (1 <= choice <= q["max"]):
            start_inactivity_timer(phone)
            await send_message(
                phone,
                f"⚠️ Invalid choice. Please reply with a number between *1* and *{q['max']}*.\n\n{q['question']}"
            )
            return

        session["data"][q["field"]] = q["options"][choice - 1]

        next_idx = idx + 1

        if next_idx < len(FLOW):
            # Advance to next question
            session["step_index"] = next_idx
            session["state"]      = FLOW[next_idx]["state"]
            save_lead(phone, session["data"], status=f"In Progress (Q{next_idx + 1})")
            start_inactivity_timer(phone)
            await send_message(phone, FLOW[next_idx]["question"])
        else:
            # All 4 questions completed! Zero friction completion
            cancel_inactivity_timer(phone)
            save_lead(phone, session["data"], status="Completed")
            session["state"] = "complete"
            await send_message(phone, THANK_YOU)
        return

    # ── Complete ───────────────────────────────────────────────────────────
    if state == "complete":
        await send_message(phone, ALREADY_DONE_MSG)
        return

    # ── Fallback ───────────────────────────────────────────────────────────
    session = reset_session(phone)
    session["state"]      = "q1_country"
    session["step_index"] = 0
    save_lead(phone, session["data"], status="In Progress (Q1)")
    start_inactivity_timer(phone)
    await send_message(phone, WELCOME_MESSAGE + "\n\n" + FLOW[0]["question"])


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 Alley Overseas WhatsApp Bot starting up...")
    _get_sheets_client()   # pre-warm Sheets connection
    get_http_client()      # pre-warm Gupshup HTTP pool
    yield
    log.info("Bot shutting down...")
    global http_client
    if http_client and not http_client.is_closed:
        await http_client.aclose()


app = FastAPI(
    title="Alley Overseas WhatsApp Bot",
    description="Study abroad lead-gen chatbot — Gupshup + Railway",
    version="2.0.0",
    lifespan=lifespan,
)


@app.post("/webhook")
async def webhook(request: Request):
    """
    Handles incoming WhatsApp messages from Gupshup (supports both Gupshup v2 and Meta v3 formats).
    """
    try:
        body = await request.json()
    except Exception:
        # Gupshup sometimes sends form-encoded / empty verification requests
        return JSONResponse({"status": "ok"})

    log.info("Incoming webhook: %s", json.dumps(body)[:400])

    sender_phone = None
    text = None
    sender_name = ""

    # Format 1: Gupshup format (v2)
    event_type = body.get("type", "")
    if event_type == "message":
        payload = body.get("payload", {})
        msg_type = payload.get("type", "")
        sender_phone = payload.get("source", "")
        sender_name = payload.get("sender", {}).get("name", "")
        if msg_type == "text":
            text = payload.get("payload", {}).get("text", "")

    # Format 2: Meta format (v3)
    elif "entry" in body:
        try:
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    for msg in messages:
                        if msg.get("type") == "text":
                            sender_phone = msg.get("from")
                            text = msg.get("text", {}).get("body")
                            # Extract name from contacts array
                            contacts = value.get("contacts", [])
                            if contacts:
                                sender_name = contacts[0].get("profile", {}).get("name", "")
        except Exception as e:
            log.warning("Failed to parse Meta v3 payload: %s", e)

    # Process message if valid sender and text extracted
    if sender_phone and text:
        await handle_message(sender_phone, text, sender_name)

    return JSONResponse({"status": "ok"})



@app.get("/webhook")
async def webhook_verify(request: Request):
    """
    Gupshup may send a GET request to verify your webhook URL.
    """
    return JSONResponse({"status": "ok", "message": "Alley Overseas bot webhook is live ✅"})


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "status": "✅ Alley Overseas WhatsApp Bot is running",
        "version": "2.0.0",
        "active_sessions": len(sessions),
        "endpoints": {"webhook": "POST /webhook", "leads": "GET /leads", "health": "GET /health"},
    }


@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(sessions)}


@app.get("/leads")
async def get_leads(request: Request):
    """Beautiful HTML dashboard for the client to view all leads."""
    from fastapi.responses import HTMLResponse

    leads = []
    if os.path.isfile(LEADS_FILE):
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                leads.append(row)

    total      = len(leads)
    completed  = sum(1 for l in leads if l.get("status") == "Completed")
    abandoned  = sum(1 for l in leads if "Abandoned" in l.get("status", ""))
    in_prog    = total - completed - abandoned

    def status_badge(s):
        if s == "Completed":
            return f'<span class="badge completed">{s}</span>'
        elif "Abandoned" in s:
            return f'<span class="badge abandoned">{s}</span>'
        else:
            return f'<span class="badge inprog">{s}</span>'

    rows_html = ""
    for i, l in enumerate(reversed(leads), 1):
        rows_html += f"""
        <tr>
          <td>{i}</td>
          <td>{l.get('timestamp','')}</td>
          <td>+{l.get('phone','')}</td>
          <td>{l.get('name','—')}</td>
          <td>{l.get('country','—')}</td>
          <td>{l.get('study_level','—')}</td>
          <td>{l.get('intake','—')}</td>
          <td>{l.get('budget','—')}</td>
          <td>{status_badge(l.get('status',''))}</td>
        </tr>"""

    if not rows_html:
        rows_html = '<tr><td colspan="9" style="text-align:center;color:#888;padding:40px;">No leads yet. Share the WhatsApp number to start collecting!</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Alley Overseas — Leads Dashboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', sans-serif; background: #f0f4f8; color: #1a202c; }}
    header {{ background: linear-gradient(135deg,#1a56db,#0e9f6e); color: white; padding: 24px 32px; }}
    header h1 {{ font-size: 1.6rem; font-weight: 700; }}
    header p  {{ font-size: 0.9rem; opacity: 0.85; margin-top: 4px; }}
    .stats {{ display: flex; gap: 16px; padding: 24px 32px; flex-wrap: wrap; }}
    .card {{ background: white; border-radius: 12px; padding: 20px 28px; flex: 1; min-width: 140px;
             box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    .card .num {{ font-size: 2rem; font-weight: 700; }}
    .card .lbl {{ font-size: 0.8rem; color: #6b7280; margin-top: 4px; }}
    .card.green .num {{ color: #0e9f6e; }}
    .card.red   .num {{ color: #e02424; }}
    .card.blue  .num {{ color: #1a56db; }}
    .card.gray  .num {{ color: #6b7280; }}
    .toolbar {{ padding: 0 32px 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }}
    .toolbar a {{ background: #1a56db; color: white; padding: 8px 18px; border-radius: 8px;
                  text-decoration: none; font-size: 0.85rem; font-weight: 600; }}
    .toolbar a:hover {{ background: #1648c7; }}
    .table-wrap {{ padding: 0 32px 40px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; background: white;
             border-radius: 12px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    th {{ background: #1a56db; color: white; padding: 12px 14px; text-align: left; font-size: 0.82rem; text-transform: uppercase; letter-spacing: .04em; }}
    td {{ padding: 11px 14px; border-bottom: 1px solid #f3f4f6; font-size: 0.88rem; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #f9fafb; }}
    .badge {{ padding: 3px 10px; border-radius: 20px; font-size: 0.76rem; font-weight: 600; }}
    .completed {{ background: #def7ec; color: #03543f; }}
    .abandoned  {{ background: #fde8e8; color: #9b1c1c; }}
    .inprog     {{ background: #e1effe; color: #1e429f; }}
    .refresh {{ font-size: 0.8rem; color: #6b7280; }}
  </style>
</head>
<body>
  <header>
    <h1>🌍 Alley Overseas — WhatsApp Leads Dashboard</h1>
    <p>Live lead data captured from your WhatsApp bot</p>
  </header>

  <div class="stats">
    <div class="card gray">  <div class="num">{total}</div>     <div class="lbl">Total Leads</div></div>
    <div class="card green"> <div class="num">{completed}</div> <div class="lbl">✅ Completed</div></div>
    <div class="card red">   <div class="num">{abandoned}</div> <div class="lbl">⚠️ Abandoned</div></div>
    <div class="card blue">  <div class="num">{in_prog}</div>   <div class="lbl">🔄 In Progress</div></div>
  </div>

  <div class="toolbar">
    <span class="refresh">🕒 Last loaded: {datetime.now().strftime('%d %b %Y, %I:%M %p')}</span>
    <a href="/leads/export">⬇️ Download CSV</a>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th><th>Date &amp; Time</th><th>WhatsApp</th><th>Name</th>
          <th>Country</th><th>Study Level</th><th>Intake</th><th>Budget</th><th>Status</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/leads/export")
async def export_leads():
    """Download leads as a CSV file."""
    from fastapi.responses import FileResponse
    if not os.path.isfile(LEADS_FILE):
        return JSONResponse({"error": "No leads yet"}, status_code=404)
    return FileResponse(
        path=LEADS_FILE,
        media_type="text/csv",
        filename=f"alley_overseas_leads_{datetime.now().strftime('%Y%m%d')}.csv",
    )


@app.delete("/leads/clear")
async def clear_leads():
    if os.path.isfile(LEADS_FILE):
        os.remove(LEADS_FILE)
    return {"status": "cleared"}

