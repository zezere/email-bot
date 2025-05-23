from datetime import datetime, timedelta, timezone
from pathlib import Path
from email_handler import EmailHandler
import email.utils
from bot import Bot
from utils import (get_message_sent_time, binary_cross_entropy, generate_message_id,
                   datetime_to_rfc, wrap_indent)
from email.message import EmailMessage
import random
import tiktoken
import numpy as np
from functools import partial
from llm_handler import EmailValidator, ResponseScheduler, EmailModerator, ResponseGenerator
from core.conversations_db import ConversationsDB


def generate_test_emails(n=3, to='acp@startup.com'):
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
    bodies.append('Hi, my name is Erin. I would like to have an accountability partner '
                  'to keep me on track with my new project. How does this work?')

    emails = []
    for i in range(n):
        msg = EmailMessage()
        msg['From'] = addresses[-1] if (i == 0) else random.choice(addresses)
        msg['To'] = to
        msg['Subject'] = subjects[-1] if (i == 0) else random.choice(subjects)
        msg['Date'] = get_random_datetime(max_age_hours=3).isoformat()
        body = bodies[-1] if (i == 0) else random.choice(bodies)
        msg.set_content(body)
        msg['Message-ID'] = generate_message_id(msg['From'], msg['Subject'], msg['Date'])
        emails.append(msg)
    return emails


def get_random_datetime(max_age_hours=3):
    """Returns a random time in the past with random time zone (tz_info)."""
    random_timezone = timezone(timedelta(seconds=random.randint(-12, 14)))
    random_delay_sec = timedelta(seconds=random.randint(0, 3600 * max_age_hours))
    return datetime.now(random_timezone) - random_delay_sec


def grab_test_conversation(topic: str):
    # DANGER: requires "data/test_conversations.py", which is not part of the repo
    # This module has conversations: {topic: [str]}
    # Each str is a message (body of an email)
    # User messages and bot messages strictly alternate
    from data.test_conversations import conversations

    print(f'Loaded conversation "{topic}" with {len(conversations[topic]['messages'])} messages.')
    return topic, conversations[topic]


def convert_messages_to_emails(topic, num_messages=None, user_address='john.doe@gmail.com',
                               bot_address='acp@startup.com', response_time=5):
    """Returns a list of emails from a ACP conversation on `topic`.

    response_time (int): delay between messages in minutes
    response_time (list): list of datetime objects for Date
    """
    # Get messages from data.test_conversations
    topic, conversation = grab_test_conversation(topic)
    messages = conversation["messages"]
    if num_messages:
        messages = messages[:num_messages]
    if "dates" in conversation:
        response_time = conversation["dates"]

    user = dict(role='user', address=user_address)
    bot = dict(role='assistant', address=bot_address)
    emails = []

    # Messages alternate between user and bot, user starts
    for i, message in enumerate(messages):
        if i % 2 == 0:
            sender, recipient = user, bot
        else:
            sender, recipient = bot, user

        msg = EmailMessage()
        msg['From'] = sender['address']
        msg['To'] = recipient['address']
        if isinstance(response_time, int):
            num_messages_that_follow = len(messages) - i
            dt = datetime.now().astimezone() - timedelta(minutes=response_time * num_messages_that_follow)
            msg['Date'] = datetime_to_rfc(dt)
        elif isinstance(response_time, list) and len(response_time) > i:
            msg['Date'] = datetime_to_rfc(response_time[i])
        else:
            raise ValueError("Have no Date for email")
        msg['Subject'] = topic
        msg.set_content(message)
        msg['Message-ID'] = generate_message_id(user['address'], msg['Subject'], msg['Date'])

        emails.append(msg)
    return emails


def fake_send_email(to_email, subject, body):
    print(f"Sending (faked) email to {to_email} ({subject}):")
    print(wrap_indent(body, width=80, indentation=8))


def test_bot():
    """Test the Bot class and its email processing functionality."""
    print("\nTesting Bot class:")
    print("-" * 50)

    # Initialize database
    init_db()

    # Create a test bot instance with simulated mail server
    bot = Bot(
        validator=EmailValidator(model_id='mistralai/mistral-7b-instruct'),
        scheduler=ResponseScheduler(model_id='mistralai/mistral-small-24b-instruct-2501'),
        generator=ResponseGenerator(model_id='deepseek/deepseek-v3-base:free'))
    bot.test = True
    bot.email_handler.email = "testbot@startup.void"
    bot.email_address = bot.email_handler.email
    bot.name = "Bot, James Bot"
    assert 'test' in bot.email_address, 'use testbot@startup.void for EMAIL in .env when testing!'

    bot.email_handler.check_inbox = partial(convert_messages_to_emails,
                                            topic="Startup Entrepreneurship",
                                            num_messages=5,
                                            bot_address=bot.email_handler.email)

    bot.email_handler.send_email = fake_send_email

    # Process new emails
    print("\nStarting email processing (process_new_emails)...")
    bot.process_new_emails()

    print("\nStarting schedule policy processing (process_schedules)...")
    bot.process_schedules()

    print("\nManage conversations (schedule_response)...")
    print(f"The bot will call scheduler_agent on {len(bot.ask_agent)} conversations")
    bot.manage_conversations()

    print(f"\nGenerating {len(bot.active_conversations)} responses (generate_response) "
          "to these conversations:")
    for i, conv in enumerate(bot.active_conversations):
        print(i, conv)
        assert conv[0] != bot.email_address, "only user_email_addresses may appear here!"
    print()

    bot.generate_responses()

    print("-" * 50)


def test_bot_v2():
    """Test the Bot class with the new ConversationsDB API.
    
    Missing database functions for testing:
    [- is_empty]
    - datetime cutoff to limit/increment the number of test messages
    """
    # Start with empty database
    Path("data/test.db").unlink(missing_ok=True)
    conv_db = ConversationsDB()

    # Add test data
    conv_db.insert_test_data()

    if not conv_db.all_replies_sent():
        print("Not all replies sent yet, returning.")
        return

    all_processes_completed = conv_db.all_processes_completed()
    if not all_processes_completed:
        if RESTART:
            print("Not all processes completed, calling bot anyway.")
        else:
            print("Not all processes completed, returning.")
            return

    bot = Bot(conv_db, test=True,
              #scheduler=ResponseScheduler(model_id='mistralai/mistral-small-3.1-24b-instruct'),
              scheduler=ResponseScheduler(model_id='meta-llama/llama-4-maverick:free'),
              #generator=ResponseGenerator(model_id='deepseek/deepseek-r1:free'),
              generator=ResponseGenerator(model_id='anthropic/claude-3.7-sonnet'),
              )

    # Step 1: set schedules & identify running conversations
    any_errors = bot.analyze_conversations()
    if any_errors:
        print("Failed to analyze all conversations, returning.")
        return

    # Step 2: write responses
    any_errors = bot.manage_running_conversations()
    if any_errors:
        print("Failed to generate or save responses for some conversations, "
              "skipping step 3 (manage_reminders).")
        return

    # Step 3: process schedules & (step 4): write reminders
    bot.manage_reminders()


def test_update_data_after_analysis():
    Path("data/test.db").unlink(missing_ok=True)
    conv_db = ConversationsDB()
    conv_db.insert_test_data()
    unanalyzed_conversations = conv_db.get_unanalyzed_conversations(track=False)
    conversation_id = unanalyzed_conversations[0]['conversation_id']

    # fails if track=False above
    conv_db.update_data_after_analysis(conversation_id, new_schedule=None, new_reply_needed=True)


def test_get_scheduled_conversations():
    Path("data/test.db").unlink(missing_ok=True)
    conv_db = ConversationsDB()
    conv_db.insert_test_data()
    scheduled_conversations = conv_db.get_scheduled_conversations(track=True)
    print(f"Found {len(scheduled_conversations)} scheduled conversations")

    # fails: sorting_timestamp is str not datetime
    for conversation in scheduled_conversations:
        for i, msg in enumerate(conversation['emails']):
            # print(f"Conversation {conversation['conversation_id']}, message {i} keys: {msg.keys()}")
            assert isinstance(msg['sorting_timestamp'], datetime), str(type(msg['sorting_timestamp']))


def test_policy_on_scheduled_conversations():
    Path("data/test.db").unlink(missing_ok=True)
    conv_db = ConversationsDB()
    conv_db.insert_test_data()
    scheduled_conversations = conv_db.get_scheduled_conversations(track=True)
    print(f"Found {len(scheduled_conversations)} scheduled conversations")

    conversation = scheduled_conversations[2]
    from scheduling import WaitForSchedulePolicy, ScheduleProcessor
    processor = ScheduleProcessor()
    reminder_policy = WaitForSchedulePolicy()
    processor.set_policy(reminder_policy)
    reply_needed = processor.process_schedule(
        conversation['conversation_id'],
        conversation['schedule'].astimezone(),  # TODO: call timezone already in conversations_db
        conversation['emails'],
        datetime.now().astimezone(),
        conversation['num_reminders'],
        conversation['last_policy'])
    assert reply_needed == 'ask agent', f"{reply_needed} != 'ask agent'"


def test_email_fetching():
    # Initialize database
    init_db()

    # Create handlers
    email_handler = EmailHandler()
    moderator = EmailModerator()

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
        is_appropriate, moderation_result = moderator.moderate_email(body)
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
    """Test validation on normal and malicious emails."""
    from bot import is_valid_email_address
    from time import perf_counter, sleep

    validator = EmailValidator(model_id='mistralai/mistral-small-24b-instruct-2501:free')
    gt_validator = EmailValidator(model_id='google/gemini-2.5-pro-exp-03-25:free')

    test_emails = generate_test_emails(100)
    test_labels = [None for _ in test_emails]

    print("\nTesting validation functionality")
    print("-" * 50)
    print(f"Validation model:   {validator.model_id}")
    print(f"Ground truth model: {gt_validator.model_id}")

    times = {'gt': [], 'valid': []}  # measure agent's total response time

    for email_msg, label in zip(test_emails, test_labels):
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
            t0 = perf_counter()
            label, gt_reasoning = gt_validator.validate_email(sender_email, subject, body)
            times['gt'].append(perf_counter() - t0)

            # Handle rate limits
            if gt_reasoning == 'wait a minute':
                print("waiting to pass rate-limit for free models...")
                sleep(60)
                t0 = perf_counter()
                label, gt_reasoning = gt_validator.validate_email(sender_email, subject, body)
                times['gt'].append(perf_counter() - t0)
            elif gt_reasoning == 'wait a day':
                print("daily rate limit for free models reached, quitting.")
                break

            if label not in {'pass', 'block'}:
                print(f"FAILED to get valid ground truth label, got {label}: {gt_reasoning}")
                continue

        # Test
        t0 = perf_counter()
        response, reasoning = validator.validate_email(sender_email, subject, body)
        times['valid'].append(perf_counter() - t0)
        if response == label:
            print(f"PASSED validation: {response}")
        else:
            print(f"FAILED validation: {response} != {label}")
            print(f"    From: {sender_email}\n    Subject: {subject}\n    Body: {body[:50]}")
            if reasoning:
                print(f"    Validation LLM's reasoning:\n{reasoning}")
            if gt_reasoning:
                print(f"    Ground-truth LLM's reasoning:\n{gt_reasoning}")

    print("Validation test finished, agent average response time:")
    if times['valid']:
        avg_time = sum(times['valid']) / len(times['valid'])
        print(f"    Validation model:   {avg_time:.1f} sec")
    if times['gt']:
        avg_time = sum(times['gt']) / len(times['gt'])
        print(f"    Ground truth model: {avg_time:.1f} sec")


def test_scheduler(emails=None, bot_address='acp@startup.com'):
    """Test scheduler agent on a conversation.

    The scheduler agent must decide whether a reponse is due given "current"
    date/time and a list of past emails from a conversation. Labels are
    generated from conversation time stamps.
    """
    scheduler = ResponseScheduler(
        model_id='openrouter/quasar-alpha'  # free+cloaked, excels at this task!
        # model_id='mistralai/mistral-small-24b-instruct-2501'  #  0.1/0.3 $/M tokens in/out
        # model_id='deepseek/deepseek-chat-v3-0324:free'  # no structured output
        # model_id='google/gemini-2.5-pro-exp-03-25:free'  # structured output, but RESOURCE_EXHAUSTED
        # model_id='google/gemini-2.0-flash-exp:free'  # OK but due/probability inconsistent
        # model_id='meta-llama/llama-3.1-8b-instruct'  # plain stupid (8b params), needs very clear prompt
        # model_id='mistralai/mistral-small-3.1-24b-instruct'  # worse
        # model_id='openai/gpt-4o-mini'  # better reasoning than mistral-small-24b-instruct,
        #                                  but also 2x more expensive
    )

    verbose = True  # print prompts
    DEBUG = False  # skip LLM calls
    exit_on_first_mistake = True

    # topic = 'Weight Loss Journey'
    # topic = 'Financial Discipline'
    # topic = 'Startup Entrepreneurship'
    # topic = 'Practicing a Hobby Goal'
    topic = 'Studying Estonian'

    test_emails = emails or convert_messages_to_emails(topic)

    print('\nTesting scheduler agents')
    print("-" * 50)
    print(f'Scheduler model:   {scheduler.model_id}')
    print(f'Conversation:      {topic} ({len(test_emails)} messages)')

    def _validate(message_history, label, bot_address, current_time,
                  verbose, DEBUG, exit_on_first_mistake=False):
        prediction = scheduler.schedule_response_v2(message_history,
                                                    bot_address=bot_address,
                                                    now=current_time,
                                                    verbose=verbose,
                                                    DEBUG=DEBUG)

        # Check for error first
        error = prediction.get('error', None)
        if error:
            print(f'ERROR: {error}')
            return None, None, error

        response_is_due = prediction['response_is_due']
        probability = prediction['probability']

        loss = binary_cross_entropy(label[1], probability)
        if response_is_due == label[0]:
            print(f"PASSED: correct   prediction for msg {i} {current_time}: {prediction}")
            acc = 1
        else:
            print(f"FAILED: incorrect prediction for msg {i} {current_time}: {prediction}, GT: {label}")
            acc = 0
            if exit_on_first_mistake:
                exit()

        return acc, loss, error

    losses, accuracies = [], []
    for i, current_msg in enumerate(test_emails):
        # Conversation to this end
        message_history = test_emails[:i + 1]

        # Set current time to 15 min after current_message's sent time (5 min may cause false negatives)
        current_time = get_message_sent_time(current_msg, debug=True) + timedelta(minutes=15)
        next_message = test_emails[i + 1] if i + 1 < len(test_emails) else None

        # Define test cases
        if next_message is None:
            if current_msg.get("From", "Unknown") == bot_address:
                break  # skip final bot message, is trivial
            label = (False, 0.0)  # assume final user message needs no response
        elif next_message.get("From", "Unknown") == bot_address:
            # Use the sent time of the next bot message as due_time
            due_time = get_message_sent_time(next_message)
            min_ahead = (due_time - current_time).total_seconds() / 60  # min to go

            if min_ahead < 90:
                # Bot should answer within 90 min or (reminder) max 90 min before schedule
                label = (True, 1.0)
            else:
                # Delayed/scheduled response, validate now, before and after bot response
                dt = current_time
                print(f"Message {i+1} is delayed, testing prediction for msg {i} at various times...")
                while dt < due_time - timedelta(minutes=90):
                    label = (False, 0.0)
                    acc, loss, error = _validate(scheduler, message_history, label,
                                                 bot_address, dt, verbose, DEBUG, exit_on_first_mistake)
                    if error:
                        break
                    accuracies.append(acc)
                    losses.append(loss)
                    dt += timedelta(days=1)

                dt = due_time + timedelta(minutes=90)
                label = (True, 1.0)
                acc, loss, error = _validate(scheduler, message_history, label,
                                             bot_address, dt, verbose, DEBUG, exit_on_first_mistake)
                if error:
                    break
                accuracies.append(acc)
                losses.append(loss)
                continue
        elif current_msg.get("From", "Unknown") == bot_address:
            continue  # skip, this works.
            label = (False, 0.0)  # no soliloquy!
        else:
            continue

        acc, loss, error = _validate(message_history, label,
                                     bot_address, current_time, verbose, DEBUG, exit_on_first_mistake)
        if error:
            break
        accuracies.append(acc)
        losses.append(loss)

    print(f"Accuracy of response_is_due:       {np.mean(accuracies):.2f}")
    print(f"Loss from predicted probabilities: {np.mean(losses):.2f}")


def test_moderation():
    """Test the moderation functionality with various types of content."""
    moderator = EmailModerator()

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
        is_appropriate, reason = moderator.moderate_email(test_case["content"])
        print(f"Result: {reason}")
        print(f"Appropriate: {is_appropriate}")
        print("-" * 50)


if __name__ == "__main__":
    # test_email_fetching()
    # test_validation()
    # test_moderation()
    # test_scheduler()
    test_bot_v2()
    # test_update_data_after_analysis()
    # test_get_scheduled_conversations()
    # test_policy_on_scheduled_conversations()