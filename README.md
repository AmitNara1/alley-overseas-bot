# 🌍 Alley Overseas — WhatsApp Lead-Gen Chatbot

> **Production-ready** WhatsApp chatbot for Alley Overseas.  
> Stack: **Python FastAPI + Gupshup WhatsApp API + Google Sheets + Railway**

---

## 📐 Architecture

```
User (WhatsApp)
      │
      ▼
Gupshup WhatsApp API  ──────►  Your Bot (FastAPI on Railway)
      │                                │
      │  ◄── reply via Gupshup API ────┘
                                       │
                              ┌────────┴────────┐
                              │                 │
                         leads.csv       Google Sheets
                         (always)        (if configured)
```

---

## 🚀 Deployment: 3-Phase Setup

---

### PHASE 1 — Gupshup WhatsApp Setup

#### Step 1.1 — Create a Gupshup Account
1. Go to [app.gupshup.io](https://app.gupshup.io) → **Sign Up** (free)
2. Verify your email

#### Step 1.2 — Create a WhatsApp App
1. Dashboard → **Create App** → Select **Access API**
2. Enter App Name: `AlleyOverseas`
3. Select **WhatsApp** as the channel

#### Step 1.3 — Connect Your WhatsApp Business Number
1. Inside your app → **Settings** → **WhatsApp Number**
2. Click **Add Number** → enter your existing WhatsApp Business number
3. Gupshup will send you a verification OTP via WhatsApp
4. Enter the OTP → ✅ Number connected

> ⚠️ **Important**: Your number must NOT be actively used in WhatsApp on a phone while connected to Gupshup API.

#### Step 1.4 — Get Your API Key
1. App Settings → **API Key** → Copy it
2. Keep it safe — you'll need it in Phase 3

---

### PHASE 2 — Google Sheets Setup (Optional but Recommended)

> Skip this phase if you only want CSV file leads.

#### Step 2.1 — Create a Google Sheet
1. Go to [sheets.google.com](https://sheets.google.com) → New Sheet
2. Name it: `Alley Overseas Leads`
3. Copy the Sheet ID from the URL:
   ```
   https://docs.google.com/spreadsheets/d/  THIS_IS_THE_ID  /edit
   ```

#### Step 2.2 — Create a Google Cloud Service Account
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use existing)
3. Enable the **Google Sheets API** and **Google Drive API**
4. Go to **IAM & Admin → Service Accounts** → **Create Service Account**
5. Name: `alley-bot` → Click through → Done
6. Click the service account → **Keys** → **Add Key** → **JSON**
7. Download the JSON file

#### Step 2.3 — Share the Sheet with the Service Account
1. Open the downloaded JSON file — copy the `client_email` field
   _(looks like: `alley-bot@your-project.iam.gserviceaccount.com`)_
2. Open your Google Sheet → **Share** → paste that email → **Editor** → Send
3. Minify the JSON file contents to a single line:
   - Open the JSON in Notepad → Select All → it's already one structure
   - Or use: [jsonminify.com](https://jsonminify.com) to compress it

---

### PHASE 3 — Deploy to Railway

#### Step 3.1 — Push Code to GitHub
```bash
cd whatsapp-qna-bot
git init
git add .
git commit -m "Initial commit — Alley Overseas bot"
# Create a GitHub repo, then:
git remote add origin https://github.com/YOUR_USERNAME/alley-overseas-bot.git
git push -u origin main
```

#### Step 3.2 — Deploy on Railway
1. Go to [railway.app](https://railway.app) → **Sign up with GitHub** (free)
2. **New Project** → **Deploy from GitHub repo**
3. Select your `alley-overseas-bot` repository
4. Railway will auto-detect Python and deploy ✅

#### Step 3.3 — Add Environment Variables on Railway
1. Your project → **Variables** tab → **+ Add Variable**
2. Add each variable:

| Variable | Value |
|----------|-------|
| `GUPSHUP_API_KEY` | Your Gupshup API key |
| `GUPSHUP_APP_NAME` | `AlleyOverseas` |
| `GUPSHUP_SOURCE` | Your WA number (e.g. `919876543210`) |
| `GOOGLE_SHEET_ID` | Your Sheet ID (Phase 2) |
| `GOOGLE_CREDS_JSON` | Entire minified service-account JSON |

3. Railway will auto-redeploy after saving variables

#### Step 3.4 — Get Your Public URL
1. Your project → **Settings** → **Domains** → **Generate Domain**
2. Copy the URL, e.g.: `https://alley-bot.railway.app`

---

### PHASE 4 — Connect Gupshup to Your Bot

#### Step 4.1 — Set the Webhook URL in Gupshup
1. Go to [app.gupshup.io](https://app.gupshup.io) → Your App (`AlleyOverseas`)
2. Click **Settings** → **Callback URL** (or **Webhook URL**)
3. Paste: `https://alley-bot.railway.app/webhook`
4. Save ✅

#### Step 4.2 — Test It! 🎉
Send **"Hi"** to your WhatsApp Business number.  
The bot should respond within seconds with the welcome message!

---

## 💬 What Users Experience

```
User:  "Hi"
Bot:   👋 Welcome to Alley Overseas! 🌟
       [Question 1 of 7 — Country selection]

User:  "2"
Bot:   [Question 2 of 7 — Study level]

...  (7 questions total) ...

Bot:   "Please enter your full name:"
User:  "Rahul Sharma"
Bot:   "Please enter your email:"
...
Bot:   🎉 Thank you! Lead saved to CSV + Google Sheets
```

---

## 🔧 Special Commands (work anytime)

| User types | Bot responds |
|-----------|-------------|
| `hi`, `hello`, `start`, `restart` | Resets and shows welcome |
| `CALL` | "We'll call you back" message |
| `AGENT` | "Connecting counsellor" message |

---

## 📊 Viewing Leads

| Method | How |
|--------|-----|
| **Google Sheets** | Open the sheet you created in Phase 2 |
| **JSON API** | `https://alley-bot.railway.app/leads` |
| **CSV file** | Download `leads.csv` from Railway's filesystem |

---

## 📁 File Overview

| File | Purpose |
|------|---------|
| `main.py` | Complete bot logic — Gupshup webhook handler |
| `requirements.txt` | Python dependencies |
| `railway.toml` | Railway deployment config |
| `.python-version` | Python 3.11 pin for Railway |
| `.env.example` | Environment variable template |
| `.gitignore` | Prevents committing secrets |
| `leads.csv` | Auto-created on first lead |

---

## 🛠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot not replying | Check Railway logs, verify webhook URL in Gupshup |
| "Gupshup returned 400" | Check `GUPSHUP_SOURCE` format — no `+`, no spaces |
| Google Sheets not updating | Verify you shared the sheet with the service account email |
| Railway build failing | Check `requirements.txt` has all packages |
| Number not connecting | Make sure number isn't logged into WhatsApp on a device |

---

## 💡 Going Further

- **Add more questions** → Edit the `FLOW` list in `main.py`
- **Change the welcome message** → Edit `WELCOME_MESSAGE` in `main.py`
- **Send lead notifications to team email** → Add `smtplib` email sending in `save_lead()`
- **Store sessions in Redis** → Replace the `sessions` dict with `redis-py` for multi-instance support

---

> Built for **Alley Overseas** 🌍 | Powered by Gupshup + Railway + FastAPI
