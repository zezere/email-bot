import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()


class EmailHandler:
    def __init__(self):
        self.email = os.getenv("EMAIL")
        self.password = os.getenv("EMAIL_PASSWORD")
        self.imap_server = "imap.zone.eu"
        self.smtp_server = "smtp.zone.eu"

    def send_email(self, to_email, subject, body):
        msg = MIMEMultipart()
        msg["From"] = self.email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(self.smtp_server, 587) as server:
            server.starttls()
            server.login(self.email, self.password)
            server.send_message(msg)

    def check_inbox(self):
        with imaplib.IMAP4_SSL(self.imap_server) as imap:
            imap.login(self.email, self.password)
            imap.select("INBOX")

            _, messages = imap.search(None, "ALL")
            emails = []

            for num in messages[0].split():
                _, msg = imap.fetch(num, "(RFC822)")
                email_body = msg[0][1]
                email_message = email.message_from_bytes(email_body)
                emails.append(email_message)

            return emails
