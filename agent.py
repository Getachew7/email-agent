import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.header import decode_header
from datetime import datetime, timedelta
from groq import Groq
import os

# ── CONFIG ───────────────────────────────────────────────
GMAIL_ADDRESS  = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASS = os.environ["GMAIL_APP_PASS"]
GROQ_API_KEY   = os.environ["GROQ_API_KEY"]
MODEL          = "llama3-8b-8192"
LOOKBACK_HOURS = 24

# Labels that will be created in your Gmail automatically
LABEL_PROCESSED  = "AI-Processed"
LABEL_NEEDS_REPLY = "Needs-Reply"
LABEL_NO_REPLY    = "No-Reply-Needed"
# ─────────────────────────────────────────────────────────

client = Groq(api_key=GROQ_API_KEY)

def ensure_label_exists(mail, label):
    """Create a Gmail label if it doesn't already exist."""
    result, folders = mail.list()
    folder_names = [f.decode().split('"/"')[-1].strip() for f in folders]
    if label not in folder_names:
        mail.create(label)
        print(f"  Created label: {label}")

def apply_label(mail, msg_id, label):
    """Apply a Gmail label to a message by copying it to that label's folder."""
    mail.copy(msg_id, label)

def fetch_unread_emails(mail):
    mail.select("inbox")
    since = (datetime.now() - timedelta(hours=LOOKBACK_HOURS)).strftime("%d-%b-%Y")
    _, message_ids = mail.search(None, f'(UNSEEN SINCE "{since}")')

    emails = []
    for mid in message_ids[0].split():
        _, msg_data = mail.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])

        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or "utf-8")

        sender = msg["From"]
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
            "sender":  sender,
            "body":    body[:3000]
        })

    return emails

def summarise_with_groq(em):
    prompt = f"""You are a concise personal email assistant.

Analyse this email and respond with exactly three sections:
SUMMARY: (one sentence)
NEEDS REPLY: (Yes or No)
SUGGESTED REPLY: (2-3 sentences if yes, "N/A" if no)

From: {em['sender']}
Subject: {em['subject']}
Body:
{em['body']}"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )
    return response.choices[0].message.content

def parse_needs_reply(summary_text):
    """Extract Yes/No from the NEEDS REPLY line."""
    for line in summary_text.splitlines():
        if line.upper().startswith("NEEDS REPLY"):
            return "YES" in line.upper()
    return False

def send_digest(summaries):
    if not summaries:
        print("No unread emails found.")
        return

    now = datetime.now().strftime("%A %d %B %Y")
    body = f"📬 Daily Email Digest — {now}\n"
    body += "=" * 50 + "\n\n"

    needs_reply_count = sum(1 for _, _, needs_reply in summaries if needs_reply)

    if needs_reply_count:
        body += f"⚠️  {needs_reply_count} email(s) need your reply — labelled 'Needs-Reply' in Gmail\n\n"

    for i, (em, summary, needs_reply) in enumerate(summaries, 1):
        flag = "🔴 REPLY NEEDED" if needs_reply else "✅ No action"
        body += f"[{i}] {em['subject']}\n"
        body += f"    From: {em['sender']}\n"
        body += f"    {flag}\n\n"
        body += f"{summary}\n"
        body += "-" * 40 + "\n\n"

    msg = MIMEText(body)
    msg["Subject"] = f"🤖 Email Digest — {datetime.now().strftime('%d %b')} ({needs_reply_count} need reply)"
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = GMAIL_ADDRESS

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
        server.send_message(msg)

    print(f"✅ Digest sent — {len(summaries)} email(s) processed, {needs_reply_count} need reply.")

def main():
    print(f"[{datetime.now().strftime('%H:%M')}] Starting email agent...")

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_ADDRESS, GMAIL_APP_PASS)

    # Make sure our labels exist before we try to use them
    for label in [LABEL_PROCESSED, LABEL_NEEDS_REPLY, LABEL_NO_REPLY]:
        ensure_label_exists(mail, label)

    emails = fetch_unread_emails(mail)
    print(f"Found {len(emails)} unread email(s).")

    summaries = []
    for em in emails:
        print(f"  → Processing: {em['subject']}")
        summary = summarise_with_groq(em)
        needs_reply = parse_needs_reply(summary)

        # Apply labels
        apply_label(mail, em["id"], LABEL_PROCESSED)
        apply_label(mail, em["id"], LABEL_NEEDS_REPLY if needs_reply else LABEL_NO_REPLY)

        summaries.append((em, summary, needs_reply))
        print(f"     {'🔴 Needs reply' if needs_reply else '✅ No action'}")

    mail.logout()
    send_digest(summaries)

if __name__ == "__main__":
    main()
