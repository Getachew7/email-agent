# 📬 AI Email Agent

An automated Gmail labelling, summarisation, and draft-reply agent powered by
[Groq](https://groq.com) and [GitHub Actions](https://github.com/features/actions).
Runs every 30 minutes — completely free, no server required.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🏷️ Auto-labelling | Classifies every unread email into 5 categories |
| 🚨 Priority senders | Configured senders are always flagged Urgent |
| 📤 Auto-unsubscribe | Detects and fires unsubscribe on newsletters automatically |
| 💬 Draft replies | Saves AI-generated replies to Gmail Drafts for your review |
| 📋 Run summary | Emails you a summary after every run |
| 📬 Daily digest | Morning summary of urgent and needs-reply emails |

### Gmail Labels Created Automatically

| Label | Meaning |
|---|---|
| `AI-Urgent` | Needs your attention today |
| `AI-Needs-Reply` | Reply when you can |
| `AI-Newsletter` | Marketing / newsletters |
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

---

## ⚙️ Configuration

Edit the config section at the top of `agent.py`:

```python
MAX_EMAILS_PER_RUN = 20       # emails processed per run
DIGEST_HOUR        = 8        # daily digest hour (UTC)

PRIORITY_SENDERS = [
    "mum@gmail.com",          # always flagged Urgent
    "boss@work.com",
]
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

Update the workflow secret in `daily.yml`:
```yaml
OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Update `agent.py` config:
```python
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
```

Install the right library in `daily.yml`:
```yaml
- run: pip install openai
```

Everything else stays identical — the OpenAI SDK uses the same
`.chat.completions.create()` interface as Groq.

### Cost Estimate (OpenAI)
Each email uses ~200 tokens. At GPT-4o mini pricing:
- 100 emails/day ≈ $0.003/day ≈ **$0.09/month**

---

## 📊 Free Tier Limits

| Service | Free Limit | Your Usage |
|---|---|---|
| GitHub Actions | 2,000 min/month | ~720 min/month |
| Groq API | 14,400 requests/day | ~20–100/day |
| Gmail IMAP | Unlimited | N/A |

---

## 🔒 Security Notes

- Credentials are stored as encrypted GitHub Secrets — never in code
- Gmail App Password has limited scope — cannot change your Google password
- Emails are processed in memory only — never written to disk or logged
- Groq does not train on API data per their privacy policy
- For highly sensitive emails (banking, legal, medical) consider adding
  those senders to a skip list

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

| Error | Fix |
|---|---|
| `model_decommissioned` | Update `MODEL` in config to `llama-3.1-8b-instant` |
| `Authentication failed` | Regenerate Gmail App Password |
| `Bad credentials` | Check GitHub Secrets are named exactly right |
| Runs taking too long | Lower `MAX_EMAILS_PER_RUN` |
| Labels not appearing | Trigger a manual run to create them |

---

## 📄 License

MIT — free to use, modify, and distribute.
