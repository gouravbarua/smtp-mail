import csv
import json
import os
import smtplib
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration
EMAILS_FILE = 'emails.csv'
STATE_FILE = 'state.json'
DAILY_LIMIT = 500
DELAY_SECONDS = 30

# SMTP Configuration (Stored in GitHub Secrets)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"last_index": -1, "emails_sent_today": 0, "last_run_date": ""}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def send_email(to_email, subject, body):
    if not EMAIL_USER or not EMAIL_PASS:
        print("Error: EMAIL_USER or EMAIL_PASS environment variables not set.")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False

def main():
    state = load_state()
    today = datetime.now().strftime('%Y-%m-%d')

    # Reset daily count if it's a new day
    if state['last_run_date'] != today:
        state['emails_sent_today'] = 0
        state['last_run_date'] = today

    if state['emails_sent_today'] >= DAILY_LIMIT:
        print("Daily limit reached. Stopping.")
        return

    emails_to_send = []
    try:
        with open(EMAILS_FILE, mode='r', encoding='utf-8') as f:
            reader = list(csv.DictReader(f))
            # Start from the next index
            start_idx = state['last_index'] + 1
            emails_to_send = reader[start_idx:]
    except Exception as e:
        print(f"Error reading emails file: {e}")
        return

    if not emails_to_send:
        print("No new emails to send.")
        return

    print(f"Found {len(emails_to_send)} new emails. Starting to send...")

    for i, row in enumerate(emails_to_send):
        if state['emails_sent_today'] >= DAILY_LIMIT:
            print("Reached daily limit during processing.")
            break

        to_email = row.get('email')
        subject = row.get('subject', 'No Subject')
        body = row.get('body', '')

        if not to_email:
            print(f"Skipping row {state['last_index'] + 1}: No email address.")
            state['last_index'] += 1
            continue

        print(f"Sending email to {to_email} ({state['emails_sent_today'] + 1}/{DAILY_LIMIT})...")
        
        if send_email(to_email, subject, body):
            state['emails_sent_today'] += 1
            state['last_index'] += 1
            save_state(state) # Save after each successful send
            print(f"Success. Waiting {DELAY_SECONDS} seconds...")
            time.sleep(DELAY_SECONDS)
        else:
            print(f"Stopping due to error.")
            break

if __name__ == "__main__":
    main()
