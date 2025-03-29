from datetime import datetime
from database import get_user, add_user, save_email, email_exists
from email_handler import EmailHandler
from llm_handler import LLMHandler
import email.utils
import re


class Bot:
    def __init__(self):
        self.email_handler = EmailHandler()
        self.llm_handler = LLMHandler()

    def process_new_emails(self):
        """Process new emails: check for harmful content and save to database."""
        emails = self.email_handler.check_inbox()
        print(f"Found {len(emails)} emails in inbox")

        for email_msg in emails:
            message_id = email_msg.get("Message-ID", "")

            # Skip if email already exists in database
            if email_exists(message_id):
                print(f"Skipping existing email: {message_id}")
                continue

            # Extract email information
            from_header = email_msg.get("From", "")
            sender_name, sender_email = email.utils.parseaddr(from_header)
            subject = email_msg.get("Subject", "")
            body = get_email_body(email_msg)
            sent_at = email_msg.get("Date", "")

            # Validate sender_email address
            if not is_valid_email_address(sender_email):
                print(f"Received invalid email address: {sender_email[:50]}")
                continue

            # Quickly validate and block spam
            response, reasoning = self.llm_handler.validate_email(sender_email, subject, body)
            if response == "pass":
                pass
            elif response == "block":
                print(f"Blocked email {message_id} from {sender_email} (spam)")
                continue
            else:
                print(f"Validation LLM did not follow instructions and responded:", response, reasoning)

            # Moderate the email content
            is_appropriate, moderation_result = self.llm_handler.moderate_email(body)
            print(f"Moderation result for {message_id}: {moderation_result}")

            # Save email information to database with moderation results
            save_email(
                message_id=message_id,
                sender_name=sender_name,
                sender_email=sender_email,
                subject=subject,
                body=body,
                sent_at=sent_at,
                is_appropriate=is_appropriate,
                moderation_reason=moderation_result,
            )
            print(f"Saved new email: {message_id} from {sender_email}")

            # Handle the email based on its content and moderation result
            if not is_appropriate:
                continue

            # Generate intelligent response for appropriate emails
            response = self.llm_handler.generate_response(body, subject, sender_name)
            print(f"Generated response for {message_id}: {response}")
            self._handle_new_user(sender_email, subject, response)

    def _handle_new_user(self, email_address, subject, response):
        # add_user(email_address, goal)
        self.email_handler.send_email(email_address, f"Re: {subject}", response)

    def _handle_user_update(self, email, update):
        user = get_user(email)
        # if user:
        #     self.email_handler.send_email(
        #         email, "Progress Update Received", "Thanks for your update! Keep going!"
        #     )

def get_email_body(email):
    if email.is_multipart():
        for part in email.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode()
    return email.get_payload(decode=True).decode()

def is_valid_email_address(email_address):
    pattern = r'^[a-zA-Z0-9._%+-]+@(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    return re.match(pattern, email_address) is not None
