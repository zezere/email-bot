from datetime import datetime
from database import get_user, add_user, save_email, email_exists
from email_handler import EmailHandler
from llm_handler import LLMHandler
import email.utils


class Bot:
    def __init__(self):
        self.email_handler = EmailHandler()
        self.llm_handler = LLMHandler()

    def process_new_emails(self):
        emails = self.email_handler.check_inbox()
        for email in emails:
            message_id = email.get("Message-ID", "")

            # Skip if email already exists in database
            if email_exists(message_id):
                continue

            # Extract email information
            sender_name, sender_email = email.utils.parseaddr(email.get("From", ""))
            subject = email.get("Subject", "")
            body = self._get_email_body(email)
            sent_at = email.get("Date", "")

            # Moderate the email content
            is_appropriate, moderation_result = self.llm_handler.moderate_email(body)

            if not is_appropriate:
                self.email_handler.send_email(
                    sender_email,
                    "Inappropriate Content Detected",
                    f"Your email was flagged as inappropriate: {moderation_result}",
                )
                continue

            # Save email information to database
            save_email(
                message_id=message_id,
                sender_name=sender_name,
                sender_email=sender_email,
                subject=subject,
                body=body,
                sent_at=sent_at,
            )

            if subject.lower() == "start":
                self._handle_new_user(sender_email, body)
            else:
                self._handle_user_update(sender_email, body)

    def _get_email_body(self, email):
        if email.is_multipart():
            for part in email.walk():
                if part.get_content_type() == "text/plain":
                    return part.get_payload(decode=True).decode()
        return email.get_payload(decode=True).decode()

    def _handle_new_user(self, email, goal):
        add_user(email, goal)
        self.email_handler.send_email(
            email,
            "Welcome to Accountability Bot!",
            f"Great! I'll help you achieve your goal: {goal}",
        )

    def _handle_user_update(self, email, update):
        user = get_user(email)
        if user:
            self.email_handler.send_email(
                email, "Progress Update Received", "Thanks for your update! Keep going!"
            )
