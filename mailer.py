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
TEMPLATE_FILE = 'template.html'
DAILY_LIMIT = 1000  # Total limit across all accounts (500 each)
DELAY_SECONDS = 30

# Global Message Template
MESSAGE_SUBJECT = "Hello from SocioTech Services!"

def load_template():
    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    return "Hello! (No template found)"

# SMTP Configuration (Multiple accounts supported)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465

# List of sender accounts
ACCOUNTS = [
    {"user": os.getenv('EMAIL_USER'), "pass": os.getenv('EMAIL_PASS')},
    {"user": os.getenv('EMAIL_USER_2'), "pass": os.getenv('EMAIL_PASS_2')}
]

# Filter out empty accounts
ACCOUNTS = [acc for acc in ACCOUNTS if acc["user"] and acc["pass"]]

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"last_index": -1, "emails_sent_today": 0, "last_run_date": ""}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def send_email(to_email, subject, body, account):
    user = account["user"]
    pw = account["pass"]
    
    if not user or not pw:
        print(f"Error: Credentials for account {user} not set.")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = user
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(user, pw)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False

def main():
    state = load_state()
    today = datetime.now().strftime('%Y-%m-%d')
    html_body = load_template()

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
        # Use global template instead of CSV columns
        subject = MESSAGE_SUBJECT
        body = html_body

        if not to_email:
            print(f"Skipping row {state['last_index'] + 1}: No email address.")
            state['last_index'] += 1
            continue

        # Rotate through available accounts
        current_account = ACCOUNTS[i % len(ACCOUNTS)]
        
        print(f"Sending email to {to_email} using {current_account['user']} ({state['emails_sent_today'] + 1}/{DAILY_LIMIT})...")
        
        if send_email(to_email, subject, body, current_account):
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
