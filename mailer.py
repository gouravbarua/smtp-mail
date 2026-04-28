import csv
import json
import os
import smtplib
import time
import urllib.parse
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client, Client

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
print(f"Loaded {len(ACCOUNTS)} sender accounts.")

# Supabase Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

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
        msg['Reply-To'] = 'info@sociotechservices.com'
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

    if not ACCOUNTS:
        print("CRITICAL ERROR: No sender accounts found! Check your GitHub Secrets (EMAIL_USER, EMAIL_PASS).")
        return

    print(f"Daily progress: {state['emails_sent_today']}/{DAILY_LIMIT} emails sent today.")
    print(f"Queue: Found {len(emails_to_send)} new emails starting from index {state['last_index'] + 1}.")

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

        # Tracking Logic
        tracking_id = None
        current_body = body
        if supabase:
            try:
                res = supabase.table('email_tracking').insert({
                    "recipient_email": to_email,
                    "subject": subject,
                    "status": "sent"
                }).execute()
                if res.data:
                    tracking_id = res.data[0]['id']
                    
                    # 1. Click Tracking for the Button
                    target_mailto = "mailto:info@sociotechservices.com?subject=Inquiry%20from%20Sociotech%20Email"
                    encoded_url = urllib.parse.quote(target_mailto)
                    click_url = f"{SUPABASE_URL}/functions/v1/track-click?id={tracking_id}&url={encoded_url}"
                    current_body = current_body.replace("{{TRACKING_LINK}}", click_url)
                    
                    # 2. Open Tracking Pixel
                    pixel_url = f"{SUPABASE_URL}/functions/v1/track-open?id={tracking_id}"
                    current_body += f'<img src="{pixel_url}" width="1" height="1" style="display:none !important;" />'
                    
                    print(f"Tracking enabled for {to_email}. ID: {tracking_id}")
            except Exception as e:
                print(f"Supabase tracking error: {e}")
        
        # Fallback if tracking failed or is disabled
        current_body = current_body.replace("{{TRACKING_LINK}}", "mailto:info@sociotechservices.com?subject=Inquiry%20from%20Sociotech%20Email")

        # Rotate through available accounts alternatively
        account_index = state['emails_sent_today'] % len(ACCOUNTS)
        current_account = ACCOUNTS[account_index]
        
        print(f"Sending email to {to_email} using {current_account['user']} ({state['emails_sent_today'] + 1}/{DAILY_LIMIT})...")
        
        if send_email(to_email, subject, current_body, current_account):
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
