"""
Auto cold email sender via Gmail SMTP.
Usage: python email_sender.py outreach.csv --from you@gmail.com --pass "app_password"
       OR set EMAIL_FROM and EMAIL_PASS env vars.

IMPORTANT: Use a Gmail App Password (not your real password).
Get one at: https://myaccount.google.com/apppasswords
Rate: ~40 emails/hour to stay safe from spam filters.
"""

import argparse
import csv
import os
import random
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def build_message(from_email: str, from_name: str, to_email: str,
                  subject: str, body: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{from_name} <{from_email}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return msg


def send_email(to_email: str, subject: str, body: str,
               from_email: str = None, password: str = None,
               from_name: str = "Qorvai AI") -> bool:
    """Send a single email via Gmail SMTP. Resolves credentials from environment."""
    import os
    import smtplib
    if not from_email:
        from_email = os.getenv("EMAIL_FROM", "")
    if not password:
        password = os.getenv("EMAIL_PASS", "")

    if not from_email or not password:
        raise ValueError("Missing EMAIL_FROM or EMAIL_PASS environment variables.")

    msg = build_message(from_email, from_name, to_email, subject, body)
    
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(from_email, password)
        smtp.send_message(msg)
    return True


def send_batch(rows: list, from_email: str, password: str, from_name: str,
               email_col: str, limit: int, delay: int):
    # Filter: has email, not already sent
    to_send = [r for r in rows
               if r.get(email_col, "").strip()
               and not r.get("sent", "").startswith("yes")]
    to_send = to_send[:limit]

    if not to_send:
        print("[!] Nothing to send — all rows already sent or missing email.")
        return 0, 0

    print(f"[*] Sending to {len(to_send)} leads | from: {from_email}")
    print(f"[*] Estimated time: ~{delay * len(to_send) // 60} min")
    print()

    sent, failed = 0, 0

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(from_email, password)

        for i, row in enumerate(to_send, 1):
            # Take first valid email if multiple separated by ;
            raw_email = row[email_col]
            candidates = [e.strip() for e in raw_email.split(";") if "@" in e]
            if not candidates:
                print(f"[{i}] SKIP — invalid email: {raw_email}")
                row["sent"] = "skip:invalid"
                continue

            to_email = candidates[0]
            subject  = (row.get("email_subject") or "Quick question").strip()
            body     = (row.get("email_body") or row.get("dm") or "").strip()
            name     = (row.get("business_name") or row.get("page_name") or to_email)[:50]

            if not body:
                print(f"[{i}] SKIP — no email body for: {name}")
                row["sent"] = "skip:no_body"
                continue

            try:
                msg = build_message(from_email, from_name, to_email, subject, body)
                smtp.send_message(msg)
                row["sent"] = "yes"
                sent += 1
                print(f"[{i}/{len(to_send)}] SENT  -> {to_email:<35} {name}")
            except Exception as e:
                row["sent"] = f"error:{e}"
                failed += 1
                print(f"[{i}/{len(to_send)}] FAIL  -> {to_email}: {e}")

            # Random delay to avoid spam detection
            if i < len(to_send):
                wait = delay + random.randint(-20, 20)
                wait = max(wait, 30)
                print(f"  sleeping {wait}s...")
                time.sleep(wait)

    return sent, failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file",                  help="CSV with email_subject, email_body, and email column")
    ap.add_argument("--from",   dest="sender",   default=os.getenv("EMAIL_FROM"), help="Your Gmail address")
    ap.add_argument("--pass",   dest="password", default=os.getenv("EMAIL_PASS"), help="Gmail App Password")
    ap.add_argument("--name",   default="Qorvai AI",   help="Sender display name (default: Qorvai AI)")
    ap.add_argument("--limit",  type=int, default=40,  help="Max emails per run (default 40)")
    ap.add_argument("--delay",  type=int, default=90,  help="Seconds between emails (default 90)")
    ap.add_argument("--col",    default="email",       help="CSV column that holds recipient email (default: email)")
    args = ap.parse_args()

    if not args.sender or not args.password:
        print("[!] Provide --from and --pass (or set EMAIL_FROM / EMAIL_PASS env vars)")
        print("    Gmail App Password: https://myaccount.google.com/apppasswords")
        sys.exit(1)

    with open(args.csv_file, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Make sure sent column exists
    for r in rows:
        r.setdefault("sent", "")

    sent, failed = send_batch(
        rows, args.sender, args.password, args.name,
        args.col, args.limit, args.delay,
    )

    # Write back with sent status
    keys = list(rows[0].keys())
    with open(args.csv_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

    print(f"\n[[OK]] Done — sent: {sent}  failed: {failed}  file updated: {args.csv_file}")


if __name__ == "__main__":
    main()
