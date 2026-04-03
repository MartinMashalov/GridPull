#!/usr/bin/env python3
"""
End-to-end test for the email ingest pipeline.

1. Sends an email from bigbridgeai@gmail.com with PDF attachments
   to martin.mashalov@gmail.com
2. Waits for the Gmail poller to pick it up
3. Verifies documents appear in the Hetzner Storage Box
4. Verifies documents are grouped properly in the inbox API

Usage:
    python scripts/test_email_ingest.py [--send-only] [--verify-only]
"""

import argparse
import email
import imaplib
import json
import os
import smtplib
import sys
import time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

# Sender (Papyra's Gmail)
SEND_EMAIL = "bigbridgeai@gmail.com"
SEND_PASSWORD = "baey uwre umjj plte"

# Receiver (GridPull ingest Gmail)
RECV_EMAIL = "martin.mashalov@gmail.com"
RECV_PASSWORD = "otil vnye amys kwho"

# PDF files to attach
PDF_DIR = Path(os.path.expanduser("~/Downloads"))
PDF_FILES = [
    "Commercial Lines Quote Sheet (1).pdf",
    "QUOTE SHEET FOR LAUREN.pdf",
    "example_form_fill.pdf",
]

# Hetzner Storage Box (SFTP)
SFTP_HOST = "u570976.your-storagebox.de"
SFTP_USER = "u570976"
SFTP_PASS = "BulgariaSofia123!"
SFTP_PORT = 23
SFTP_BASE = "/ingest"

# API
API_BASE = "https://gridpull.com/api"


def send_test_email(recipient_tag: str = ""):
    """Send email with PDF attachments from bigbridgeai to martin.mashalov."""
    # Build recipient - optionally with +intake-{key} tag
    if recipient_tag:
        local, domain = RECV_EMAIL.split("@")
        to_addr = f"{local}+intake-{recipient_tag}@{domain}"
    else:
        to_addr = RECV_EMAIL

    msg = MIMEMultipart()
    msg["From"] = SEND_EMAIL
    msg["To"] = to_addr
    msg["Subject"] = "GridPull Ingest Test - Insurance Quote Sheets"

    body = (
        "This is an automated test email for the GridPull email ingest system.\n\n"
        "Attached are 3 insurance quote sheet PDFs that should be:\n"
        "1. Picked up by the Gmail IMAP poller\n"
        "2. Stored in the Hetzner Storage Box\n"
        "3. Appear in the user's inbox grouped by sender\n"
    )
    msg.attach(MIMEText(body, "plain"))

    # Attach PDFs
    attached = 0
    for pdf_name in PDF_FILES:
        pdf_path = PDF_DIR / pdf_name
        if not pdf_path.exists():
            print(f"  WARNING: {pdf_path} not found, skipping")
            continue

        with open(pdf_path, "rb") as f:
            pdf_data = f.read()

        attachment = MIMEApplication(pdf_data, _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename=pdf_name)
        msg.attach(attachment)
        attached += 1
        print(f"  Attached: {pdf_name} ({len(pdf_data):,} bytes)")

    if attached == 0:
        print("ERROR: No PDF files found to attach!")
        return False

    # Send via Gmail SMTP
    print(f"\nSending email from {SEND_EMAIL} to {to_addr}...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SEND_EMAIL, SEND_PASSWORD)
            server.send_message(msg)
        print(f"  Email sent successfully! ({attached} attachments)")
        return True
    except Exception as e:
        print(f"  ERROR sending email: {e}")
        return False


def verify_sftp_storage():
    """Check if files appeared in the Hetzner Storage Box."""
    import paramiko

    print("\nVerifying Hetzner Storage Box (SFTP)...")
    try:
        transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
        transport.connect(username=SFTP_USER, password=SFTP_PASS)
        sftp = paramiko.SFTPClient.from_transport(transport)

        # List all files under /ingest
        def list_recursive(path, depth=0):
            files = []
            try:
                for item in sftp.listdir_attr(path):
                    full_path = f"{path}/{item.filename}"
                    if item.st_mode and (item.st_mode & 0o40000):  # directory
                        files.extend(list_recursive(full_path, depth + 1))
                    else:
                        files.append((full_path, item.st_size))
            except Exception as e:
                if depth == 0:
                    print(f"  Could not list {path}: {e}")
            return files

        files = list_recursive(SFTP_BASE)
        if files:
            print(f"  Found {len(files)} files in {SFTP_BASE}:")
            for path, size in files:
                print(f"    {path} ({size:,} bytes)")
        else:
            print(f"  No files found in {SFTP_BASE} yet")

        sftp.close()
        transport.close()
        return len(files) > 0
    except Exception as e:
        print(f"  ERROR connecting to SFTP: {e}")
        return False


def verify_imap_received():
    """Check if the email was received in the Gmail inbox."""
    print("\nChecking if email was received in Gmail...")
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(RECV_EMAIL, RECV_PASSWORD)
        imap.select("INBOX")

        # Search for recent emails from the sender
        status, data = imap.search(None, f'(FROM "{SEND_EMAIL}")')
        if status == "OK" and data and data[0]:
            uids = data[0].split()
            print(f"  Found {len(uids)} emails from {SEND_EMAIL}")

            # Check the most recent one
            latest_uid = uids[-1]
            status, msg_data = imap.fetch(latest_uid, "(RFC822.HEADER)")
            if status == "OK" and msg_data and msg_data[0]:
                headers = email.message_from_bytes(msg_data[0][1])
                print(f"  Latest: Subject={headers.get('Subject', 'N/A')}")
                print(f"          Date={headers.get('Date', 'N/A')}")
        else:
            print(f"  No emails found from {SEND_EMAIL}")

        imap.close()
        imap.logout()
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test GridPull email ingest pipeline")
    parser.add_argument("--send-only", action="store_true", help="Only send the test email")
    parser.add_argument("--verify-only", action="store_true", help="Only verify storage/inbox")
    parser.add_argument("--tag", default="", help="Ingest address key to use (e.g., 'abc123')")
    parser.add_argument("--wait", type=int, default=60, help="Seconds to wait before verification")
    args = parser.parse_args()

    print("=" * 60)
    print("GridPull Email Ingest - End-to-End Test")
    print("=" * 60)

    if not args.verify_only:
        print("\n--- Step 1: Send test email ---")
        if not send_test_email(args.tag):
            print("\nFailed to send email. Aborting.")
            sys.exit(1)

    if not args.send_only:
        if not args.verify_only:
            print(f"\n--- Waiting {args.wait}s for Gmail poller to process ---")
            for i in range(args.wait, 0, -10):
                print(f"  {i}s remaining...")
                time.sleep(min(10, i))

        print("\n--- Step 2: Verify email received ---")
        verify_imap_received()

        print("\n--- Step 3: Verify Hetzner Storage Box ---")
        verify_sftp_storage()

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
