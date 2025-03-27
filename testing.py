from database import init_db
from email_handler import EmailHandler
import email.utils
from database import save_email, email_exists
from llm_handler import LLMHandler
from bot import Bot, get_email_body
from email.message import EmailMessage
import random
import tiktoken


def get_test_emails(n=5, to='acp@startup.com'):
    """Returns a list of fake emails: invalid, spam, and legitimate."""
    addresses = [
        'asdlfkj21313@hotmail.c',  # invalid address
        'john.doe@gmail.com',  # spam
        'erink@openai.com',  # legit
    ]
    subjects = [
        'alsidlidfsa',
        '',
        'ACP for my new project',
    ]
    word_counts = [20, 30]
    # generate random content
    tokenizer = tiktoken.get_encoding("cl100k_base")
    vocab_size = tokenizer.n_vocab
    bodies = [tokenizer.decode([random.randint(0, vocab_size - 1) for _ in range(n)]) for n in word_counts]
    bodies.append('Hi, my name is Erin. I would like to have an accountability partner to keep me on track with my new project. How does this work?')

    emails = []
    for _ in range(n):
        msg = EmailMessage()
        msg['From'] = random.choice(addresses)
        msg['To'] = to
        msg['Message-Id'] = '202503252000.' + str(random.randint(0, 1000000))
        msg['Subject'] = random.choice(subjects)
        msg.set_content(random.choice(bodies))
        emails.append(msg)
    return emails


def test_bot():
    """Test the Bot class and its email processing functionality."""
    print("\nTesting Bot class:")
    print("-" * 50)

    # Initialize database
    init_db()

    # Create bot instance
    bot = Bot()

    # If mail server is no configured in .env, test with fake mails
    if bot.email_handler.email is None:
        print("Using fake emails for testing.")
        bot.email_handler.check_inbox = get_test_emails

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

def test_validation():
    """Test validation on normal and malicious emails.

    Tested models:
    - mistralai/mistral-small-24b-instruct-2501:free
    - google/gemma-2-9b-it:free  sometimes returns empty response
    """
    from bot import is_valid_email_address

    llm_handler = LLMHandler()
    validation_model = 'mistralai/mistral-small-24b-instruct-2501:free'
    gt_model = 'deepseek/deepseek-chat-v3-0324:free'

    test_emails = get_test_emails(10)
    test_labels = [None for _ in test_emails]

    print("\nTesting validation functionality")
    print("-" * 50)
    print(f"Validation model: {validation_model}")
    print(f"Ground truth: {gt_model}")

    for email_msg, label in zip(test_emails, test_labels):
        message_id = email_msg.get("Message-ID", "")

        # Extract email information
        from_header = email_msg.get("From", "")
        sender_name, sender_email = email.utils.parseaddr(from_header)
        subject = email_msg.get("Subject", "")
        body = get_email_body(email_msg)

        # Check sender_email address
        if not is_valid_email_address(sender_email):
            print(f"SKIPPED invalid email {sender_email}")
            continue  # not to be handled by LLM validation

        # Get label
        gt_reasoning = ''
        if label is None:
            label, gt_reasoning = llm_handler.validate_email(sender_email, subject, body, model_id=gt_model)
            if label not in {'pass', 'block'}:
                print(f"FAILED to get valid ground truth label, got {gt_reasoning}")
                continue

        # Test
        response, reasoning = llm_handler.validate_email(sender_email, subject, body, model_id=validation_model)
        if response == label:
            print(f"PASSED validation: {response}")
        else:
            print(f"FAILED validation: {response} != {label}")
            print(f"    From: {sender_email}\n    Subject: {subject}\n    Body: {body[:50]}")
            if reasoning:
                print(f"    Validation LLM's reasoning:\n{reasoning}")
            if gt_reasoning:
                print(f"    Ground-truth LLM's reasoning:\n{gt_reasoning}")

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
    # test_validation()
    # test_moderation()
    test_bot()
