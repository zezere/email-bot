from database import init_db
from email_handler import EmailHandler
import email.utils
from database import save_email, email_exists


def _get_email_body(email_msg):
    if email_msg.is_multipart():
        for part in email_msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode()
    return email_msg.get_payload(decode=True).decode()


def test_email_fetching():
    # Initialize database
    init_db()

    # Create email handler
    email_handler = EmailHandler()

    # Fetch emails
    emails = email_handler.check_inbox()

    # Process each email
    for email_msg in emails:
        message_id = email_msg.get("Message-ID", "")

        # Skip if email already exists in database
        if email_exists(message_id):
            print(f"Skipping existing email: {message_id}")
            continue

        # Extract email information
        sender_name, sender_email = email.utils.parseaddr(email_msg.get("From", ""))
        subject = email_msg.get("Subject", "")
        body = _get_email_body(email_msg)
        sent_at = email_msg.get("Date", "")

        # Save email information to database
        save_email(
            message_id=message_id,
            sender_name=sender_name,
            sender_email=sender_email,
            subject=subject,
            body=body,
            sent_at=sent_at,
        )
        print(f"Saved new email: {message_id} from {sender_email}")


if __name__ == "__main__":
    test_email_fetching()
