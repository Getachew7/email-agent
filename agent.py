import imaplib
import smtplib
import email
import urllib.request
import re
import os
from email.mime.text import MIMEText
from email.header import decode_header
from datetime import datetime
from groq import Groq

# ── CONFIG ───────────────────────────────────────────────
GMAIL_ADDRESS  = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASS = os.environ["GMAIL_APP_PASS"]
GROQ_API_KEY   = os.environ["GROQ_API_KEY"]
MODEL          = "llama-3.1-8b-instant"
DIGEST_HOUR    = 8   # 8AM UTC = 9AM BST

# Add senders who should ALWAYS be flagged Urgent
PRIORITY_SENDERS = [
    "mebiratu21@gmail.com",
    "info@destaintelligence.com",
    # add any email address here
]

LABELS = {
    "URGENT":       "AI-Urgent",
    "NEEDS-REPLY":  "AI-Needs-Reply",
    "NEWSLETTER":   "AI-Newsletter",
    "NOTIFICATION": "AI-Notification",
    "NO-ACTION":    "AI-No-Action",
}

ICONS = {
    "URGENT":       "🚨",
    "NEEDS-REPLY":  "🔴",
    "NEWSLETTER":   "📰",
    "NOTIFICATION": "🔔",
    "NO-ACTION":    "✅",
}
# ─────────────────────────────────────────────────────────

client = Groq(api_key=GROQ_API_KEY)

# ── GMAIL HELPERS ─────────────────────────────────────────

def ensure_labels(mail):
    _, folders = mail.list()
    existing = [f.decode().split('"/"')[-1].strip() for f in folders]
    for label in LABELS.values():
        if label not in existing:
            mail.create(label)
            print(f"  Created label: {label}")

def apply_label(mail, msg_id, label):
    mail.copy(msg_id, label)

def fetch_unread_emails(mail):
    mail.select("inbox")
    _, message_ids = mail.search(None, "UNSEEN")

    emails = []
    if not message_ids[0]:
        return emails

    for mid in message_ids[0].split():
        _, msg_data = mail.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])

        subject, enc = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(enc or "utf-8")

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

        emails.append({
            "id":          mid,
            "subject":     subject,
            "sender":      msg.get("From", ""),
            "reply_to":    msg.get("Reply-To", msg.get("From", "")),
            "body":        body[:2000],
            "unsubscribe": msg.get("List-Unsubscribe", ""),
        })

    return emails

# ── CLASSIFICATION ────────────────────────────────────────

def classify_email(em):
    # Priority sender override — skip AI entirely
    sender_lower = em["sender"].lower()
    if any(p.lower() in sender_lower for p in PRIORITY_SENDERS):
        print(f"     ⭐ Priority sender — forced URGENT")
        return "URGENT"

    prompt = f"""Classify this email into EXACTLY one category:
URGENT          - needs reply today (deadlines, emergencies, direct questions from real people)
NEEDS-REPLY     - needs reply but not urgent (personal messages, questions, conversations)
NEWSLETTER      - marketing, promotions, or newsletters
NOTIFICATION    - automated system alerts (GitHub, Google, social media notifications)
NO-ACTION       - informational only, no reply needed

IMPORTANT RULES:
- If a real person asks you a direct question → NEEDS-REPLY or URGENT
- If it starts with Hi/Hey/Hello from a real person → at least NEEDS-REPLY
- Automated service emails → NOTIFICATION
- Promotional/marketing emails → NEWSLETTER

From: {em['sender']}
Subject: {em['subject']}
Body: {em['body'][:500]}

Reply with ONE word only."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10
    )
    result = response.choices[0].message.content.strip().upper()
    for key in LABELS:
        if key in result:
            return key
    return "NO-ACTION"

# ── AUTO-UNSUBSCRIBE ──────────────────────────────────────

def auto_unsubscribe(em):
    """Use List-Unsubscribe header to unsubscribe from newsletters."""
    header = em.get("unsubscribe", "")
    if not header:
        return False

    # Try mailto unsubscribe
    mailto = re.search(r'<mailto:([^>]+)>', header)
    if mailto:
        parts = mailto.group(1).split("?")
        to_addr = parts[0]
        subject = "unsubscribe"
        if len(parts) > 1:
            s = re.search(r'subject=([^&]+)', parts[1], re.I)
            if s:
                subject = s.group(1)
        try:
            msg = MIMEText("")
            msg["Subject"] = subject
            msg["From"]    = GMAIL_ADDRESS
            msg["To"]      = to_addr
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
                server.send_message(msg)
            return True
        except:
            pass

    # Try HTTP unsubscribe
    http = re.search(r'<(https?://[^>]+)>', header)
    if http:
        try:
            urllib.request.urlopen(http.group(1), timeout=5)
            return True
        except:
            pass

    return False

# ── AUTO-REPLY ────────────────────────────────────────────

def draft_auto_reply(em):
    """Ask AI whether this email is simple enough to auto-reply to."""
    prompt = f"""You are a personal email assistant.

Decide if this email is simple enough for an auto-reply.
Auto-reply if: casual greeting, "how are you", simple yes/no question, meeting confirmation.
Do NOT auto-reply if: work tasks, legal/financial, anything requiring real thought.

From: {em['sender']}
Subject: {em['subject']}
Body: {em['body'][:500]}

Respond in this exact format:
DECISION: YES or NO
REPLY: (2-3 sentence friendly reply, or NO-AUTO-REPLY)"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150
    )
    content = response.choices[0].message.content.strip()

    if "DECISION: YES" in content:
        match = re.search(r'REPLY:\s*(.+)', content, re.DOTALL)
        if match:
            reply = match.group(1).strip()
            if reply != "NO-AUTO-REPLY":
                return reply
    return None

def send_auto_reply(em, reply_text):
    msg = MIMEText(reply_text)
    msg["Subject"] = f"Re: {em['subject']}"
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = em["reply_to"]
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
        server.send_message(msg)

# ── DAILY DIGEST ──────────────────────────────────────────

def send_daily_digest(summaries):
    if not summaries:
        return

    urgent      = [e for e, c in summaries if c == "URGENT"]
    needs_reply = [e for e, c in summaries if c == "NEEDS-REPLY"]
    newsletters = [e for e, c in summaries if c == "NEWSLETTER"]

    now  = datetime.now().strftime("%A %d %B %Y")
    body = f"📬 Daily Email Digest — {now}\n"
    body += "=" * 50 + "\n\n"

    if urgent:
        body += f"🚨 URGENT — {len(urgent)} email(s) need attention today\n"
        for e in urgent:
            body += f"   • {e['subject']} — {e['sender']}\n"
        body += "\n"

    if needs_reply:
        body += f"🔴 NEEDS REPLY — {len(needs_reply)} email(s)\n"
        for e in needs_reply:
            body += f"   • {e['subject']} — {e['sender']}\n"
        body += "\n"

    if newsletters:
        body += f"📰 NEWSLETTERS UNSUBSCRIBED — {len(newsletters)}\n"
        for e in newsletters:
            body += f"   • {e['subject']} — {e['sender']}\n"
        body += "\n"

    counts = {}
    for _, cat in summaries:
        counts[cat] = counts.get(cat, 0) + 1

    body += "📊 Full breakdown\n"
    for cat, count in counts.items():
        body += f"   {ICONS[cat]} {cat}: {count}\n"

    msg = MIMEText(body)
    msg["Subject"] = (
        f"🤖 Daily Digest — {datetime.now().strftime('%d %b')} "
        f"({len(urgent)} urgent, {len(needs_reply)} to reply)"
    )
    msg["From"] = GMAIL_ADDRESS
    msg["To"]   = GMAIL_ADDRESS

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
        server.send_message(msg)
    print("📬 Daily digest sent.")

# ── MAIN ──────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting email agent...")
    is_digest_time = datetime.utcnow().hour == DIGEST_HOUR

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
    ensure_labels(mail)

    emails = fetch_unread_emails(mail)
    print(f"Found {len(emails)} unread email(s).")

    summaries = []

    for em in emails:
        print(f"  → {em['subject'][:60]}")

        category = classify_email(em)
        apply_label(mail, em["id"], LABELS[category])
        print(f"     {ICONS[category]} {category}")

        # Auto-unsubscribe newsletters
        if category == "NEWSLETTER" and em["unsubscribe"]:
            success = auto_unsubscribe(em)
            print(f"     {'📤 Unsubscribed' if success else '⚠️  Unsubscribe failed'}")

        # Auto-reply simple personal emails
        if category in ["URGENT", "NEEDS-REPLY"]:
            reply = draft_auto_reply(em)
            if reply:
                send_auto_reply(em, reply)
                print(f"     💬 Auto-reply sent")

        summaries.append((em, category))

    mail.logout()

    # Send digest once a day at 9AM BST
    if is_digest_time:
        send_daily_digest(summaries)

    print("Done.")

if __name__ == "__main__":
    main()
