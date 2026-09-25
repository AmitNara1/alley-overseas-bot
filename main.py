"""
Alley Overseas — WhatsApp Lead-Gen Chatbot v2.0
================================================
Stack : FastAPI + Gupshup WhatsApp API + Google Sheets
Deploy: Railway (always-on, free tier)
Author: Built with Antigravity AI
"""

import csv
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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
                ["Timestamp", "Phone", "Country", "Study Level", "Intake",
                 "Qualification", "English Test", "Budget", "Help Type",
                 "Full Name", "Email", "Mobile", "City"],
                value_input_option="RAW",
            )
        ws.append_row(row, value_input_option="RAW")
        log.info("Lead appended to Google Sheet ✅")
    except Exception as exc:
        log.error("Failed to append to Sheet: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# CSV FALLBACK STORAGE
# ─────────────────────────────────────────────────────────────────────────────

LEADS_FILE = "leads.csv"
CSV_HEADERS = [
    "timestamp", "phone", "country", "study_level", "intake",
    "qualification", "english_test", "budget", "help_type",
    "name", "email", "mobile", "city",
]


def save_lead_csv(phone: str, data: dict) -> None:
    file_exists = os.path.isfile(LEADS_FILE)
    with open(LEADS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        row = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "phone": phone}
        row.update({k: data.get(k, "") for k in CSV_HEADERS[2:]})
        writer.writerow(row)
    log.info("Lead saved to leads.csv ✅")


def save_lead(phone: str, data: dict) -> None:
    """Save to both CSV (always) and Google Sheets (if configured)."""
    save_lead_csv(phone, data)
    sheet_row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        phone,
        data.get("country", ""),
        data.get("study_level", ""),
        data.get("intake", ""),
        data.get("qualification", ""),
        data.get("english_test", ""),
        data.get("budget", ""),
        data.get("help_type", ""),
        data.get("name", ""),
        data.get("email", ""),
        data.get("mobile", ""),
        data.get("city", ""),
    ]
    append_to_sheet(sheet_row)


# ─────────────────────────────────────────────────────────────────────────────
# GUPSHUP OUTBOUND MESSAGING
# ─────────────────────────────────────────────────────────────────────────────

GUPSHUP_API_URL = "https://api.gupshup.io/wa/api/v1/msg"


async def send_message(destination: str, text: str) -> None:
    """
    Send a WhatsApp text message via Gupshup.
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
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(GUPSHUP_API_URL, data=payload, headers=headers)
            if resp.status_code == 202:
                log.info("Message sent to %s ✅", destination)
            else:
                log.warning("Gupshup returned %s: %s", resp.status_code, resp.text)
    except Exception as exc:
        log.error("Failed to send message: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATION FLOW DEFINITION
# ─────────────────────────────────────────────────────────────────────────────

FLOW = [
    {
        "state": "q1_country",
        "question": (
            "🌍 *Question 1 of 7*\n"
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
            "📚 *Question 2 of 7*\n"
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
            "📅 *Question 3 of 7*\n"
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
        "state": "q4_qualification",
        "question": (
            "🎓 *Question 4 of 7*\n"
            "What is your highest qualification?\n\n"
            "1️⃣ 12th Grade\n"
            "2️⃣ Diploma\n"
            "3️⃣ Bachelor's\n"
            "4️⃣ Master's\n"
            "5️⃣ Other\n\n"
            "_Reply with a number (1–5)_"
        ),
        "options": ["12th Grade", "Diploma", "Bachelor's", "Master's", "Other"],
        "field": "qualification",
        "max": 5,
    },
    {
        "state": "q5_english",
        "question": (
            "🗣️ *Question 5 of 7*\n"
            "Have you taken any English language test?\n\n"
            "1️⃣ IELTS\n"
            "2️⃣ PTE\n"
            "3️⃣ TOEFL\n"
            "4️⃣ Duolingo\n"
            "5️⃣ Not Yet\n\n"
            "_Reply with a number (1–5)_"
        ),
        "options": ["IELTS", "PTE", "TOEFL", "Duolingo", "Not Yet"],
        "field": "english_test",
        "max": 5,
    },
    {
        "state": "q6_budget",
        "question": (
            "💰 *Question 6 of 7*\n"
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
    {
        "state": "q7_help",
        "question": (
            "🤝 *Question 7 of 7*\n"
            "How would you like us to help?\n\n"
            "1️⃣ University Selection\n"
            "2️⃣ Admission Process\n"
            "3️⃣ Scholarship Guidance\n"
            "4️⃣ Visa Assistance\n"
            "5️⃣ Education Loan\n"
            "6️⃣ Everything\n\n"
            "_Reply with numbers (e.g. *1, 3, 4* or *6* for all)_"
        ),
        "options": ["University Selection", "Admission Process", "Scholarship Guidance", "Visa Assistance", "Education Loan", "Everything"],
        "field": "help_type",
        "max": 6,
        "allow_multiple": True,
    },
]

FLOW_STATE_MAP: dict[str, int] = {q["state"]: i for i, q in enumerate(FLOW)}

LEAD_FIELDS = [
    {"state": "lead_name",   "question": "✏️ Please enter your *full name*:\n_(e.g. Rahul Sharma)_",          "field": "name"},
    {"state": "lead_email",  "question": "📧 Please enter your *email address*:\n_(e.g. rahul@gmail.com)_",   "field": "email"},
    {"state": "lead_mobile", "question": "📱 Please enter your *mobile number*:\n_(e.g. 9876543210)_",        "field": "mobile"},
    {"state": "lead_city",   "question": "🏙️ Please enter your *city*:\n_(e.g. Mumbai, Delhi, Ahmedabad)_",   "field": "city"},
]

LEAD_STATE_MAP: dict[str, int] = {lf["state"]: i for i, lf in enumerate(LEAD_FIELDS)}

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

It takes less than *1 minute*. Let's get started! 🚀
━━━━━━━━━━━━━━━━━━━━━━"""

LEAD_INTRO = "🙌 Almost there! Just a few details so our counsellor can reach you:"

THANK_YOU = """\
🎉 *Thank You!*

Your information has been received. ✅

One of our study abroad experts will contact you *shortly*.

━━━━━━━━━━━━━━━━━━━━━━
Need immediate assistance?

📞 Reply *CALL* → Request a call back
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
🎉 You've already submitted your details!

Our team will contact you soon.

📞 Reply *CALL* to request a call back
💬 Reply *AGENT* to chat with a counsellor

_Type *restart* to start over._"""


# ─────────────────────────────────────────────────────────────────────────────
# IN-MEMORY SESSIONS
# ─────────────────────────────────────────────────────────────────────────────

sessions: dict[str, dict] = {}


def get_session(phone: str) -> dict:
    if phone not in sessions:
        sessions[phone] = {"state": "start", "step_index": -1, "lead_step": -1, "data": {}}
    return sessions[phone]


def reset_session(phone: str) -> dict:
    sessions[phone] = {"state": "start", "step_index": -1, "lead_step": -1, "data": {}}
    return sessions[phone]


# ─────────────────────────────────────────────────────────────────────────────
# CORE MESSAGE HANDLER
# ─────────────────────────────────────────────────────────────────────────────

async def handle_message(phone: str, raw_text: str) -> None:
    """Process an incoming WhatsApp message and send the appropriate reply."""
    body     = raw_text.strip()
    body_low = body.lower()
    session  = get_session(phone)

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

    state = session["state"]

    # ── START → show welcome + Q1 ──────────────────────────────────────────
    if state == "start":
        session["state"] = "q1_country"
        session["step_index"] = 0
        await send_message(phone, WELCOME_MESSAGE + "\n\n" + FLOW[0]["question"])
        return

    # ── Q1–Q7 numbered-choice questions ───────────────────────────────────
    if state in FLOW_STATE_MAP:
        idx = session["step_index"]
        q   = FLOW[idx]

        if q.get("allow_multiple", False):
            # Parse multiple numbers (e.g. "1, 3, 4", "1 3 4", "1,2", "6")
            raw_parts = [p.strip() for p in body.replace(",", " ").replace("&", " ").replace("+", " ").split()]
            selected_indices = []
            for p in raw_parts:
                try:
                    c = int(p)
                    if 1 <= c <= q["max"]:
                        if c not in selected_indices:
                            selected_indices.append(c)
                except ValueError:
                    pass

            if not selected_indices:
                await send_message(
                    phone,
                    f"⚠️ Please reply with one or more numbers between 1 and {q['max']} (e.g. *1, 3, 4* or *6*).\n\n{q['question']}"
                )
                return

            # If "Everything" (option 6) is selected or all options selected
            if len(q["options"]) in selected_indices:
                selected_labels = "Everything"
            else:
                selected_labels = ", ".join([q["options"][i - 1] for i in selected_indices])

            session["data"][q["field"]] = selected_labels
        else:
            try:
                choice = int(body)
            except ValueError:
                await send_message(
                    phone,
                    f"⚠️ Please reply with a *number* between 1 and {q['max']}.\n\n{q['question']}"
                )
                return

            if not (1 <= choice <= q["max"]):
                await send_message(
                    phone,
                    f"⚠️ Invalid choice. Please reply with a number between *1* and *{q['max']}*.\n\n{q['question']}"
                )
                return

            session["data"][q["field"]] = q["options"][choice - 1]

        next_idx = idx + 1

        if next_idx < len(FLOW):
            session["step_index"] = next_idx
            session["state"]      = FLOW[next_idx]["state"]
            await send_message(phone, FLOW[next_idx]["question"])
        else:
            session["state"]     = "lead_name"
            session["lead_step"] = 0
            await send_message(phone, LEAD_INTRO + "\n\n" + LEAD_FIELDS[0]["question"])
        return

    # ── Lead-capture free-text fields ─────────────────────────────────────
    if state in LEAD_STATE_MAP:
        ls    = session["lead_step"]
        field = LEAD_FIELDS[ls]

        if len(body) < 2:
            await send_message(phone, f"⚠️ Please enter a valid response.\n\n{field['question']}")
            return

        session["data"][field["field"]] = body
        next_ls = ls + 1

        if next_ls < len(LEAD_FIELDS):
            session["lead_step"] = next_ls
            session["state"]     = LEAD_FIELDS[next_ls]["state"]
            await send_message(phone, LEAD_FIELDS[next_ls]["question"])
        else:
            save_lead(phone, session["data"])
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
    await send_message(phone, WELCOME_MESSAGE + "\n\n" + FLOW[0]["question"])


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 Alley Overseas WhatsApp Bot starting up...")
    _get_sheets_client()   # pre-warm Sheets connection
    yield
    log.info("Bot shutting down.")


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

    # Format 1: Gupshup format (v2)
    event_type = body.get("type", "")
    if event_type == "message":
        payload = body.get("payload", {})
        msg_type = payload.get("type", "")
        sender_phone = payload.get("source", "")
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
        except Exception as e:
            log.warning("Failed to parse Meta v3 payload: %s", e)

    # Process message if valid sender and text extracted
    if sender_phone and text:
        await handle_message(sender_phone, text)

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
async def get_leads():
    """View all captured leads as JSON."""
    if not os.path.isfile(LEADS_FILE):
        return {"leads": [], "total": 0}
    leads = []
    with open(LEADS_FILE, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            leads.append(row)
    return {"leads": leads, "total": len(leads)}


@app.delete("/leads/clear")
async def clear_leads():
    if os.path.isfile(LEADS_FILE):
        os.remove(LEADS_FILE)
    return {"status": "cleared"}
