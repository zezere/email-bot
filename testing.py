from database import init_db
from email_handler import EmailHandler
import email.utils
from database import save_email, email_exists
from llm_handler import LLMHandler
from bot import Bot, get_email_body


def test_bot():
    """Test the Bot class and its email processing functionality."""
    print("\nTesting Bot class:")
    print("-" * 50)

    # Initialize database
    init_db()

    # Create bot instance
    bot = Bot()

    # Process new emails
    print("Starting email processing...")
    bot.process_new_emails()
    print("Email processing completed")
    print("-" * 50)


def test_email_fetching():
    # Initialize database
    init_db()

    # Create handlers
    email_handler = EmailHandler()
    llm_handler = LLMHandler()

    # Fetch emails
    emails = email_handler.check_inbox()
    print(f"Found {len(emails)} emails in inbox")

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
        body = get_email_body(email_msg)
        sent_at = email_msg.get("Date", "")

        # Moderate the email content
        is_appropriate, moderation_result = llm_handler.moderate_email(body)
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


def test_moderation():
    """Test the moderation functionality with various types of content."""
    llm_handler = LLMHandler()

    # Test cases
    test_cases = [
        {
            "content": "I want to achieve my goal of running a marathon next month.",
            "description": "Appropriate content about personal goals",
        },
        {
            "content": "I hate everyone and want to hurt them.",
            "description": "Harmful content",
        },
        {
            "content": "I want to learn Python programming and build a project.",
            "description": "Appropriate content about learning",
        },
        {"content": "I want to commit suicide.", "description": "Self-harm content"},
    ]

    print("\nTesting moderation functionality:")
    print("-" * 50)

    for test_case in test_cases:
        print(f"\nTest case: {test_case['description']}")
        print(f"Content: {test_case['content']}")
        is_appropriate, reason = llm_handler.moderate_email(test_case["content"])
        print(f"Result: {reason}")
        print(f"Appropriate: {is_appropriate}")
        print("-" * 50)


if __name__ == "__main__":
    # test_email_fetching()
    # test_moderation()
    test_bot()
