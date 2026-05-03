import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
from groq import Groq
import os

# ── CONFIG ───────────────────────────────────────────────
GMAIL_ADDRESS  = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASS = os.environ["GMAIL_APP_PASS"]
GROQ_API_KEY   = os.environ["GROQ_API_KEY"]
MODEL          = "llama-3.1-8b-instant"
LOOKBACK_MINS  = 6

LABELS = {
    "URGENT":       "AI-Urgent",
    "NEEDS-REPLY":  "AI-Needs-Reply",
    "NEWSLETTER":   "AI-Newsletter",
    "NOTIFICATION": "AI-Notification",
    "NO-ACTION":    "AI-No-Action",
}
# ─────────────────────────────────────────────────────────

client = Groq(api_key=GROQ_API_KEY)

def ensure_labels(mail):
    result, folders = mail.list()
    existing = [f.decode().split('"/"')[-1].strip() for f in folders]
    for label in LABELS.values():
        if label not in existing:
            mail.create(label)
            print(f"  Created label: {label}")

def apply_label(mail, msg_id, label):
    mail.copy(msg_id, label)

def fetch_unread_emails(mail):
    mail.select("inbox")
    since = (datetime.now() - timedelta(minutes=LOOKBACK_MINS)).strftime("%d-%b-%Y")
    _, message_ids = mail.search(None, f'(UNSEEN SINCE "{since}")')

    emails = []
    if not message_ids[0]:
        return emails

    for mid in message_ids[0].split():
        _, msg_data = mail.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])

        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or "utf-8")

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

        emails.append({
            "id":      mid,
            "subject": subject,
            "sender":  msg["From"],
            "body":    body[:500]
        })

    return emails

def classify_email(em):
    prompt = f"""Classify this email into EXACTLY one category:
URGENT          - needs reply today
NEEDS-REPLY     - needs reply but not urgent
NEWSLETTER      - marketing or newsletter
NOTIFICATION    - automated system notification
NO-ACTION       - informational, no reply needed

From: {em['sender']}
Subject: {em['subject']}
Body: {em['body']}

Reply with ONE word only."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=10
    )

    result = response.choices[0].message.content.strip().upper()

    # Match response to a known label key
    for key in LABELS:
        if key in result:
            return key

    return "NO-ACTION"  # safe fallback if AI responds unexpectedly

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking inbox...")

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_ADDRESS, GMAIL_APP_PASS)

    ensure_labels(mail)

    emails = fetch_unread_emails(mail)
    print(f"Found {len(emails)} new unread email(s).")

    icons = {
        "URGENT":       "🚨",
        "NEEDS-REPLY":  "🔴",
        "NEWSLETTER":   "📰",
        "NOTIFICATION": "🔔",
        "NO-ACTION":    "✅",
    }

    for em in emails:
        print(f"  → {em['subject'][:60]}")
        category = classify_email(em)
        label = LABELS[category]
        apply_label(mail, em["id"], label)
        print(f"     {icons[category]} {label}")

    mail.logout()
    print("Done.")

if __name__ == "__main__":
    main()
