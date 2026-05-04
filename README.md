# 📬 AI Email Agent

An automated Gmail labelling, draft-reply, unsubscribe, and digest agent powered by
[Groq](https://groq.com) and [GitHub Actions](https://github.com/features/actions).
Runs every 30 minutes — completely free, no server required.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🏷️ Auto-labelling | Classifies every unread email into 5 categories using AI |
| 🚨 Priority senders | Configured senders are always flagged Urgent, bypassing AI |
| 📤 Auto-unsubscribe | Detects and fires unsubscribe on newsletters automatically |
| 💬 Draft replies | Drafts replies for all email types — casual, work, legal, scheduling, complaints. Saves to Gmail Drafts for your review — nothing sends automatically |
| 📋 Run summary | Emails you a full summary after every run showing what was processed, unsubscribed, and drafted |
| 📬 Daily digest | Morning summary of urgent and needs-reply emails sent once per day |

### Gmail Labels Created Automatically

| Label | Meaning |
|---|---|
| `AI-Urgent` | Needs your attention today |
| `AI-Needs-Reply` | Reply when you can |
| `AI-Newsletter` | Marketing / newsletters (auto-unsubscribed) |
| `AI-Notification` | Automated system alerts |
| `AI-No-Action` | No action needed |

---

## 🏗️ Architecture

```
GitHub Actions (cron every 30 min)
        │
    agent.py
        │
   ┌────┴────┐
   │  Gmail  │  ← IMAP (read) + SMTP (summary email, drafts)
   └────┬────┘
        │
   ┌────┴────┐
   │  Groq   │  ← llama-3.1-8b-instant (classify + draft)
   └─────────┘
```

**Email window:** Each run processes unread emails from the **last 48 hours** only —
old mail is never touched, and anything missed yesterday is caught today.

---

## 🚀 Setup Guide

### 1. Get a Groq API Key
1. Sign up at [console.groq.com](https://console.groq.com) (free, no credit card)
2. Go to **API Keys → Create API Key**
3. Save the key

### 2. Create a Gmail App Password
1. Go to your Google Account → **Security**
2. Enable **2-Step Verification** if not already on
3. Search for **App Passwords** → generate one named `email-agent`
4. Save the 16-character password

### 3. Create the GitHub Repository
1. Go to [github.com/new](https://github.com/new)
2. Name it `email-agent` — set to **Private**
3. Tick **Add a README** and click **Create**

### 4. Add Repository Secrets
Go to **Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|---|---|
| `GMAIL_ADDRESS` | your full Gmail address |
| `GMAIL_APP_PASS` | 16-character app password |
| `GROQ_API_KEY` | Groq API key from Step 1 |

### 5. Add the Files
Create these two files in your repo:

**`agent.py`** — the main agent script (see source)

**`.github/workflows/daily.yml`**:
```yaml
name: Daily Email Agent

on:
  schedule:
    - cron: '*/30 * * * *'
  workflow_dispatch:

jobs:
  run-agent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install groq
      - name: Run email agent
        env:
          GMAIL_ADDRESS:  ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASS: ${{ secrets.GMAIL_APP_PASS }}
          GROQ_API_KEY:   ${{ secrets.GROQ_API_KEY }}
        run: python agent.py
```

### 6. Test It
Go to **Actions → Daily Email Agent → Run workflow**

You should receive a run summary email in your inbox within 2–4 minutes.

---

## ⚙️ Configuration

Edit the config section at the top of `agent.py`:

```python
MAX_EMAILS_PER_RUN = 20       # max emails processed per run — keep at 20 to avoid timeouts
DIGEST_HOUR        = 8        # daily digest hour in UTC (8 = 9AM BST)

# Senders always flagged Urgent regardless of email content
PRIORITY_SENDERS = [
    "mum@gmail.com",
    "boss@work.com",
]

# Senders that will NEVER receive a draft reply (automated/notification senders)
NO_DRAFT_SENDERS = [
    "notification",
    "noreply",
    "no-reply",
    "donotreply",
    "facebookmail.com",
    "slack.com",
    "linkedin.com",
    "twitter.com",
    "instagram.com",
    "github.com",
]
```

### Why MAX_EMAILS_PER_RUN = 20?
Each email makes 2 Groq API calls (classify + draft). At 20 emails per run, the job
completes in under 2 minutes. GitHub Actions free tier jobs become unreliable above
6 minutes. The agent runs every 30 minutes so your inbox stays current without
needing large batch sizes.

---

## 💬 How Draft Replies Work

The agent drafts replies for **all** emails classified as `AI-Urgent` or `AI-Needs-Reply`.
It detects the email type and adjusts tone and length automatically:

| Email type | Tone | Length |
|---|---|---|
| Casual / personal | Friendly, conversational | 2–3 sentences |
| Work / project update | Professional, clear | 4–6 sentences |
| Legal / financial | Formal, measured | 4–6 sentences |
| Meeting / scheduling | Courteous, concise | 3–4 sentences |
| Job application | Professional, enthusiastic | 4–5 sentences |
| Complaint | Empathetic, solution-focused | 4–5 sentences |
| Urgent | Direct, action-oriented | 3–5 sentences |

All drafts are saved to your **Gmail Drafts folder**. Nothing is ever sent automatically.
Known automated senders (Slack, Facebook, LinkedIn etc.) are excluded from drafting.
Duplicate drafts are prevented — if a draft already exists for a subject it is skipped.

---

## 📋 Run Summary Email

After every run you receive a summary email showing:

- Total emails processed with a breakdown by category
- List of newsletters that were auto-unsubscribed
- List of draft replies saved to your Drafts folder
- Reminder to check Drafts before sending

Example subject line:
```
🤖 Agent Run — 20 processed, 8 unsub'd, 3 drafts
```

---

## 🔄 Switching to OpenAI API

If you prefer to use OpenAI (GPT-4o mini) instead of Groq:

### 1. Get an OpenAI API Key
1. Sign up at [platform.openai.com](https://platform.openai.com)
2. Go to **API Keys → Create new secret key**
3. Add it as a GitHub Secret named `OPENAI_API_KEY`

### 2. Update `agent.py`

Replace the import and client setup:

```python
# Remove this:
from groq import Groq
client = Groq(api_key=GROQ_API_KEY)

# Add this:
from openai import OpenAI
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
```

Change the model in the config:
```python
MODEL = "gpt-4o-mini"   # cheap, fast, accurate
```

Update `agent.py` config:
```python
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
```

Update the workflow secret in `daily.yml`:
```yaml
OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Install the right library in `daily.yml`:
```yaml
- run: pip install openai
```

Everything else stays identical — the OpenAI SDK uses the same
`.chat.completions.create()` interface as Groq.

### Cost Estimate (OpenAI)
Each email uses ~300 tokens (classify + draft). At GPT-4o mini pricing:
- 100 emails/day ≈ $0.004/day ≈ **$0.12/month**

---

## 📊 Free Tier Limits

| Service | Free Limit | Your Usage |
|---|---|---|
| GitHub Actions | 2,000 min/month | ~720 min/month |
| Groq API | 14,400 requests/day | ~40–200/day |
| Gmail IMAP | Unlimited | N/A |

---

## 🔒 Security Notes

- Credentials are stored as encrypted GitHub Secrets — never in code
- Gmail App Password has limited scope — cannot change your Google password
- Emails are processed in memory only — never written to disk or logged
- Groq does not train on API data per their privacy policy
- Known automated senders are excluded from AI draft replies
- For highly sensitive emails (banking, legal, medical) add those senders
  to `NO_DRAFT_SENDERS` to prevent drafting

---

## 📁 Repository Structure

```
email-agent/
├── .github/
│   └── workflows/
│       └── daily.yml      # GitHub Actions schedule
├── agent.py               # Main agent logic
└── README.md              # This file
```

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| `model_decommissioned` error | Update `MODEL` to `llama-3.1-8b-instant` |
| `Authentication failed` | Regenerate Gmail App Password |
| `Bad credentials` | Check GitHub Secrets are named exactly right |
| Runs taking too long / timing out | Set `MAX_EMAILS_PER_RUN = 20` |
| Labels not appearing in Gmail | Trigger a manual run to create them |
| Old emails being processed | Check `fetch_unread_emails` uses `UNSEEN SINCE yesterday` |
| Duplicate drafts appearing | Ensure `already_drafted()` check is in `main()` |
| Wrong emails getting drafted | Add sender domain to `NO_DRAFT_SENDERS` list |
| Scheduled runs not firing | GitHub can delay up to 30 min — wait and refresh Actions tab |

---

## 📄 License

MIT — free to use, modify, and distribute.
