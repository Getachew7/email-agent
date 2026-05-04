import imaplib
import smtplib
import email
import urllib.request
import re
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from datetime import datetime, timedelta
from groq import Groq

# ── CONFIG ───────────────────────────────────────────────
GMAIL_ADDRESS      = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASS     = os.environ["GMAIL_APP_PASS"]
GROQ_API_KEY       = os.environ["GROQ_API_KEY"]
MODEL              = "llama-3.1-8b-instant"
DIGEST_HOUR        = 8        # 8 UTC = 9AM BST
MAX_EMAILS_PER_RUN = 50

# Senders that should NEVER get a draft reply
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

PRIORITY_SENDERS = [
    "mebiratu21@gmail.com",
    "info@destaintelligence.com",
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
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
    _, message_ids = mail.search(None, f'(UNSEEN SINCE "{yesterday}")')

    emails = []
    if not message_ids[0]:
        return emails

    all_ids = message_ids[0].split()
    recent_ids = all_ids[-MAX_EMAILS_PER_RUN:]

    for mid in recent_ids:
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

# ── SAVE DRAFT ────────────────────────────────────────────

def save_draft(mail, em, reply_text):
    """Save a reply as a Gmail draft instead of sending it."""
    msg = MIMEMultipart()
    msg["Subject"] = f"Re: {em['subject']}"
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = em["reply_to"]
    msg.attach(MIMEText(reply_text, "plain"))

    # Append to Gmail Drafts folder
    mail.append(
        "[Gmail]/Drafts",
        "",
        imaplib.Time2Internaldate(datetime.now().timestamp()),
        msg.as_bytes()
    )

# ── CLASSIFICATION ────────────────────────────────────────

def classify_email(em):
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
- If a real person asks a direct question → NEEDS-REPLY or URGENT
- If it starts with Hi/Hey/Hello from a real person → at least NEEDS-REPLY
- Automated service emails → NOTIFICATION
- Promotional or marketing emails → NEWSLETTER

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
    header = em.get("unsubscribe", "")
    if not header:
        return False

    mailto = re.search(r'<mailto:([^>]+)>', header)
    if mailto:
        parts    = mailto.group(1).split("?")
        to_addr  = parts[0]
        subject  = "unsubscribe"
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

    http = re.search(r'<(https?://[^>]+)>', header)
    if http:
        try:
            urllib.request.urlopen(http.group(1), timeout=5)
            return True
        except:
            pass

    return False

# ── DRAFT REPLY ───────────────────────────────────────────

def draft_reply(em, category):
    """Draft a reply for all emails needing a response — simple or complex."""

    if category == "URGENT":
        tone = "urgent and professional"
        length = "3-5 sentences"
        detail = "Acknowledge the urgency, address the key point directly, and confirm next steps or your availability."
    elif category == "NEEDS-REPLY":
        tone = "friendly and conversational"
        length = "2-3 sentences"
        detail = "Respond naturally as if you are the recipient replying to a friend or colleague."
    else:
        return None

    # Detect email type for tailored instructions
    body_lower = em["body"].lower()
    subject_lower = em["subject"].lower()

    if any(w in body_lower + subject_lower for w in ["invoice", "payment", "contract", "legal", "agreement", "solicitor", "lawyer"]):
        tone = "formal and professional"
        length = "4-6 sentences"
        detail = "Acknowledge receipt, confirm you have reviewed the matter, state any initial position or questions clearly, and indicate when a full response will follow."

    elif any(w in body_lower + subject_lower for w in ["meeting", "call", "schedule", "available", "availability", "interview"]):
        tone = "professional and courteous"
        length = "3-4 sentences"
        detail = "Confirm your interest, suggest available times or ask for their availability, and keep it concise."

    elif any(w in body_lower + subject_lower for w in ["job", "application", "position", "role", "hire", "cv", "resume"]):
        tone = "professional and enthusiastic"
        length = "4-5 sentences"
        detail = "Express genuine interest, briefly highlight relevant experience, and suggest next steps such as a call or interview."

    elif any(w in body_lower + subject_lower for w in ["complaint", "issue", "problem", "unhappy", "disappointed", "refund"]):
        tone = "empathetic and professional"
        length = "4-5 sentences"
        detail = "Acknowledge the issue, apologise where appropriate, explain what steps will be taken, and provide a timeframe for resolution."

    elif any(w in body_lower + subject_lower for w in ["project", "task", "deadline", "deliverable", "update", "status"]):
        tone = "professional and clear"
        length = "4-6 sentences"
        detail = "Acknowledge the request, provide a clear status update or response to each point raised, and confirm any next steps or deadlines."

    prompt = f"""You are a professional personal email assistant drafting a reply on behalf of the recipient.

Email details:
From: {em['sender']}
Subject: {em['subject']}
Body:
{em['body'][:1000]}

Instructions:
- Tone: {tone}
- Length: {length}
- {detail}
- Write in first person as if you are the recipient
- Do NOT include a subject line
- Do NOT include placeholders like [Your Name] — end the email naturally
- Start directly with the reply content, no preamble

Write the draft reply now:"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )
    return response.choices[0].message.content.strip()

# ── RUN SUMMARY EMAIL ─────────────────────────────────────

def send_run_summary(mail, processed, unsubscribed, drafted):
    """Send a short summary of what the agent did this run."""
    if not processed:
        print("  No emails processed — skipping summary.")
        return

    now  = datetime.now().strftime("%H:%M on %d %b %Y")
    body = f"🤖 Email Agent Run Summary — {now}\n"
    body += "=" * 50 + "\n\n"

    body += f"📊 Processed {len(processed)} email(s) this run:\n"
    for cat in LABELS:
        count = sum(1 for _, c in processed if c == cat)
        if count:
            body += f"   {ICONS[cat]} {cat}: {count}\n"

    if unsubscribed:
        body += f"\n📤 Unsubscribed from {len(unsubscribed)} newsletter(s):\n"
        for sender, subject in unsubscribed:
            body += f"   • {subject[:60]} — {sender}\n"

    if drafted:
        body += f"\n💬 {len(drafted)} draft reply(s) saved to your Drafts folder:\n"
        for sender, subject in drafted:
            body += f"   • Re: {subject[:60]} — {sender}\n"
        body += "\n   ➜ Check Gmail Drafts, review and send when ready.\n"

    body += "\n" + "-" * 50
    body += f"\nNext run in ~30 minutes."

    msg = MIMEText(body)
    msg["Subject"] = (
        f"🤖 Agent Run — {len(processed)} processed"
        + (f", {len(unsubscribed)} unsub'd" if unsubscribed else "")
        + (f", {len(drafted)} drafts" if drafted else "")
    )
    msg["From"] = GMAIL_ADDRESS
    msg["To"]   = GMAIL_ADDRESS

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
        server.send_message(msg)
    print("📋 Run summary sent.")

# ── DAILY DIGEST ──────────────────────────────────────────

def send_daily_digest(processed):
    if not processed:
        return

    urgent      = [(e, c) for e, c in processed if c == "URGENT"]
    needs_reply = [(e, c) for e, c in processed if c == "NEEDS-REPLY"]
    newsletters = [(e, c) for e, c in processed if c == "NEWSLETTER"]

    now  = datetime.now().strftime("%A %d %B %Y")
    body = f"📬 Daily Email Digest — {now}\n"
    body += "=" * 50 + "\n\n"

    if urgent:
        body += f"🚨 URGENT — {len(urgent)} email(s) need attention today\n"
        for e, _ in urgent:
            body += f"   • {e['subject']} — {e['sender']}\n"
        body += "\n"

    if needs_reply:
        body += f"🔴 NEEDS REPLY — {len(needs_reply)} email(s)\n"
        for e, _ in needs_reply:
            body += f"   • {e['subject']} — {e['sender']}\n"
        body += "\n"

    if newsletters:
        body += f"📰 NEWSLETTERS UNSUBSCRIBED — {len(newsletters)}\n"
        for e, _ in newsletters:
            body += f"   • {e['subject']} — {e['sender']}\n"
        body += "\n"

    counts = {}
    for _, cat in processed:
        counts[cat] = counts.get(cat, 0) + 1

    body += "📊 Full breakdown:\n"
    for cat, count in counts.items():
        body += f"   {ICONS[cat]} {cat}: {count}\n"

    msg = MIMEText(body)
    msg["Subject"] = (
        f"📬 Daily Digest — {datetime.now().strftime('%d %b')} "
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
    print(f"Found {len(emails)} unread email(s) to process.")

    processed    = []   # list of (email, category)
    unsubscribed = []   # list of (sender, subject)
    drafted      = []   # list of (sender, subject)

    for em in emails:
        print(f"  → {em['subject'][:60]}")

        category = classify_email(em)
        apply_label(mail, em["id"], LABELS[category])
        print(f"     {ICONS[category]} {category}")

        # Auto-unsubscribe newsletters
        if category == "NEWSLETTER" and em["unsubscribe"]:
            success = auto_unsubscribe(em)
            if success:
                unsubscribed.append((em["sender"], em["subject"]))
                print(f"     📤 Unsubscribed")
            else:
                print(f"     ⚠️  Unsubscribe failed")

        # Save draft reply — skip known automated senders
        sender_lower = em["sender"].lower()
        is_automated = any(x in sender_lower for x in NO_DRAFT_SENDERS)
        
        if category in ["URGENT", "NEEDS-REPLY"] and not is_automated:
            reply = draft_reply(em, category)
            if reply:
                save_draft(mail, em, reply)
                drafted.append((em["sender"], em["subject"]))
                print(f"     💬 Draft reply saved")

        processed.append((em, category))

    # Always send run summary if anything was processed
    send_run_summary(mail, processed, unsubscribed, drafted)

    # Send full daily digest once a day at digest hour
    if is_digest_time:
        send_daily_digest(processed)

    mail.logout()
    print("Done.")

if __name__ == "__main__":
    main()
