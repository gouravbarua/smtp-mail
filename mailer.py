import csv
import json
import os
import smtplib
import time
import logging
import urllib.parse
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client, Client

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Configuration
EMAILS_FILE = 'emails.csv'
STATE_FILE = 'state.json'
TEMPLATE_FILE = 'template.html'
DAILY_LIMIT = 1000  # Total limit across all accounts (500 each)
DELAY_SECONDS = 30

# Global Message Templates
MESSAGE_SUBJECT = "Transform Your Business with sociotech services"

TEXT_TEMPLATE = """
Hello,

For years, transportation companies have focused on operations. Now it's time to grow online with SOCIOTECH.

We help transport, trucking, courier, cargo and logistics businesses build their online presence and automate operations.

Our Services:
- Professional Websites
- Logo & Branding
- Custom Fleet Management Software
- Professional Email Setup
- Digital Growth & SEO
- Hosting & Security

LIMITED OFFER: First 50 customers get FREE services worth $199+

Reply to this email or visit www.sociotechservices.com to get started.

Best regards,
The SOCIOTECH Team
"""

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
logger.info(f"Loaded {len(ACCOUNTS)} sender accounts.")

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

def send_email(to_email, subject, body, account, is_html=True):
    user = account["user"]
    pw = account["pass"]
    
    if not user or not pw:
        logger.error(f"Credentials for account {user} not set.")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = user
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['Reply-To'] = 'info@sociotechservices.com'
        
        # Attach body based on format
        mime_type = 'html' if is_html else 'plain'
        msg.attach(MIMEText(body, mime_type))

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(user, pw)
            server.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email} via {user}: {e}")
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
        logger.info("Daily limit reached. Stopping.")
        return

    emails_to_send = []
    try:
        with open(EMAILS_FILE, mode='r', encoding='utf-8') as f:
            reader = list(csv.DictReader(f))
            # Start from the next index
            start_idx = state['last_index'] + 1
            emails_to_send = reader[start_idx:]
    except Exception as e:
        logger.error(f"Error reading emails file: {e}")
        return

    # Fetch Unsubscribe List
    unsubscribed_emails = set()
    if supabase:
        try:
            res = supabase.table('unsubscribes').select('email').execute()
            unsubscribed_emails = {row['email'] for row in res.data}
            logger.info(f"Loaded {len(unsubscribed_emails)} unsubscribed emails.")
        except Exception as e:
            logger.warning(f"Could not fetch unsubscribe list: {e}")

    if not emails_to_send:
        logger.info("No new emails to send.")
        return

    if not ACCOUNTS:
        logger.critical("No sender accounts found! Check your GitHub Secrets (EMAIL_USER, EMAIL_PASS).")
        return

    logger.info(f"Daily progress: {state['emails_sent_today']}/{DAILY_LIMIT} emails sent today.")
    logger.info(f"Queue: Found {len(emails_to_send)} new emails starting from index {state['last_index'] + 1}.")

    for i, row in enumerate(emails_to_send):
        if state['emails_sent_today'] >= DAILY_LIMIT:
            logger.info("Reached daily limit during processing.")
            break

        to_email = row.get('email')
        
        # Determine format (0-199: HTML, 200-399: Text)
        current_index = state['last_index'] + 1
        is_html = True
        
        if 0 <= current_index < 200:
            is_html = True
            current_format = "HTML"
        elif 200 <= current_index < 400:
            is_html = False
            current_format = "Text"
        else:
            # Default to HTML for anything after 400, or you can adjust this
            is_html = True
            current_format = "HTML"

        # Check Unsubscribe List
        if to_email in unsubscribed_emails:
            logger.info(f"Skipping {to_email}: Unsubscribed.")
            state['last_index'] += 1
            continue
            
        # Use global template instead of CSV columns
        subject = MESSAGE_SUBJECT
        body = html_body

        if not to_email:
            logger.warning(f"Skipping row {state['last_index'] + 1}: No email address.")
            state['last_index'] += 1
            continue

        # Tracking & Body Logic
        tracking_id = None
        current_body = html_body if is_html else TEXT_TEMPLATE
        
        if supabase:
            try:
                res = supabase.table('email_tracking').insert({
                    "recipient_email": to_email,
                    "subject": subject,
                    "status": "sent"
                }).execute()
                if res.data:
                    tracking_id = res.data[0]['id']
                    
                    if is_html:
                        # 1. Click Tracking for the Button
                        target_mailto = "mailto:info@sociotechservices.com?subject=Book%20a%20Demo"
                        encoded_url = urllib.parse.quote(target_mailto)
                        click_url = f"{SUPABASE_URL}/functions/v1/track-click?id={tracking_id}&url={encoded_url}"
                        current_body = current_body.replace("{{TRACKING_LINK}}", click_url)
                        
                        # 2. Open Tracking Pixel
                        pixel_url = f"{SUPABASE_URL}/functions/v1/track-open?id={tracking_id}"
                        current_body += f'<img src="{pixel_url}" width="1" height="1" style="display:none !important;" />'
                        
                        # 3. Unsubscribe Link
                        unsub_url = f"{SUPABASE_URL}/functions/v1/unsubscribe?email={urllib.parse.quote(to_email)}"
                        current_body = current_body.replace("{{UNSUB_LINK}}", unsub_url)
                    else:
                        # For Text emails, we just append a simple unsub link at the end
                        unsub_url = f"{SUPABASE_URL}/functions/v1/unsubscribe?email={urllib.parse.quote(to_email)}"
                        current_body += f"\n\nUnsubscribe: {unsub_url}"
                    
                    logger.info(f"Tracking enabled for {to_email} [{current_format}]. ID: {tracking_id}")
            except Exception as e:
                logger.error(f"Supabase tracking error: {e}")
        
        # Fallback placeholders for HTML
        if is_html:
            current_body = current_body.replace("{{TRACKING_LINK}}", "mailto:info@sociotechservices.com?subject=Book%20a%20Demo")
            current_body = current_body.replace("{{UNSUB_LINK}}", "#")

        # Rotate through available accounts alternatively
        account_index = state['emails_sent_today'] % len(ACCOUNTS)
        current_account = ACCOUNTS[account_index]
        
        logger.info(f"Sending {current_format} email to {to_email} using {current_account['user']} ({state['emails_sent_today'] + 1}/{DAILY_LIMIT})...")
        
        if send_email(to_email, subject, current_body, current_account, is_html):
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
