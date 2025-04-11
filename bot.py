from time import perf_counter
from datetime import datetime
from database import save_email, save_moderation, email_exists, get_all_schedules, get_emails, set_schedule
from email_handler import EmailHandler
from llm_handler import LLMHandler
import email.utils
from scheduling import ScheduleProcessor, REMINDER_POLICIES, choose_policy
from utils import is_valid_email_address, get_email_body, get_message_sent_time


class Bot:
    """
    - Fetches new emails, validates, moderates, and saves them in the database
    - Manages conversations, identified by (user_email_address, email_subject)
    - Conversations that require immediate response are called "active".
    - Generates and sends reponse emails for active conversations and scheduled
      reminders and saves them in the database.

    If the bot crashes at any moment, it can be restarted with the database in
    its current state.
    """
    def __init__(self):
        self.email_handler = EmailHandler()
        self.email_address = self.email_handler.email  # bot address from .env
        self.llm_handler = LLMHandler()
        self.active_conversations = set()  # (user_email_address, subject)
        self.ask_agent = set()  # conversations handled by schedule_response agent

    def process_new_emails(self):
        """Process new emails: check for harmful content and save to database."""
        start_time = perf_counter()
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
            sent_at = get_message_sent_time(email_msg)

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
                print("Validation LLM did not follow instructions. Response: "
                      f"{response}, {reasoning}")

            # Moderate the email content
            is_appropriate, moderation_result = self.llm_handler.moderate_email(body)
            # is_appropriate = True
            if not is_appropriate:
                print(f"Moderation result for {message_id}: {moderation_result}")
                save_moderation(
                    message_id=message_id,
                    timestamp=sent_at,
                    sender_name=sender_name,
                    from_email_address=sender_email,
                    to_email_address=self.email_address,
                    email_subject=subject,
                    email_body=body,
                    email_sent=True,
                )
                print(f"Saved new email from {sender_email} ({subject}). "
                      f"Delay: {(datetime.now().astimezone() - sent_at).seconds / 60:.1f} min")

            # schedule_response agent needs to decide: respond or set/update schedule?
            self.ask_agent.add((sender_email, subject))

        print(f"Processing new emails completed in {perf_counter() - start_time:.1f} sec.")

    def process_schedules(self):
        """Update active_conversations according to schedules and reminder policy."""
        schedules = get_all_schedules()
        print(f"Database returned {len(schedules)} scheduled conversations.")

        processor = ScheduleProcessor()

        for schedule in schedules:
            user, subject, due_time, reminder_sent = schedule
            just_got_user_mail = (user, subject) in self.active_conversations
            messages = get_emails(user, subject)
            now = datetime.now().astimezone()

            # Variant (A): try all policies, apply the first that works
            for reminder_policy in REMINDER_POLICIES:
                processor.set_policy(reminder_policy)
                try:
                    response_is_due = processor.process_schedule(schedule, just_got_user_mail,
                                                                 messages, now)
                    print(f"reminder_policy {reminder_policy.name} was successful.")
                    break
                except Exception as e:
                    print(f"reminder_policy {reminder_policy.name} failed with {e}")
                    print(f"    schedule: {schedule}")
                    print(f"    last message: {messages[-1]}")

            # Variant (B): use a sophisticated choose_policy function
            # reminder_policy = choose_policy(schedule, just_got_user_mail, messages, now)
            # processor.set_policy(reminder_policy)
            # response_is_due = processor.process_schedule(schedule, just_got_user_mail,
            #                                              messages, now)

            if response_is_due is True:
                # Policy says that a response is due right now
                self.active_conversations.add((user, subject))
                continue
            elif response_is_due is False:
                # Schedule does not trigger anything
                continue
            else:
                # Let the schedule_response agent decide what to do
                self.ask_agent.add((user, subject))

    def manage_conversations(self):
        """Let schedule_response agent handle potentially active conversations."""
        llm_handler = LLMHandler()

        for user_email_address, email_subject in self.ask_agent:
            messages = get_emails(user_email_address, email_subject)

            result = llm_handler.schedule_response_v2(messages, bot_address=self.email_address,
                                                      now=None, verbose=False, DEBUG=False)

            if 'error' in result:
                print(f"schedule_response agent failed with {result['error']} "
                      f"({user_email_address}, '{email_subject}')")
                # On error, fall back to default: respond to user
                self.active_conversations.add((user_email_address, email_subject))
            elif result['response_is_due']:
                self.active_conversations.add((user_email_address, email_subject))
                print("result: response IS due, added conv to active_conversations "
                      f"({user_email_address}, '{email_subject}').")
            else:
                print(f"result: response is not due ({user_email_address}, '{email_subject}')")
                print(result)
                print(", setting schedule...")
                set_schedule(user_email_address, email_subject, result['scheduled_for'])

            # Future: go full probabilistic
            if hasattr(self, 'chattiness') and result['probability'] > (1 - self.chattiness):
                self.active_conversations.add((user_email_address, email_subject))

    def generate_responses(self):
        """Reply in all active_conversations."""
        llm_handler = LLMHandler()

        for user_email_address, email_subject in self.active_conversations:
            messages = get_emails(user_email_address, email_subject)

            email_body = llm_handler.generate_response(
                user_email_address, self.email_address, email_subject, messages)

            if not email_body:
                print(f"generate_response agent failed generating response to "
                      f"{user_email_address} ({email_subject})")
                print("Last message:")
                print(messages[-1])
                # TODO: Send mail to devs...
                continue

            # Save email information to database
            timestamp = datetime.now().astimezone()
            save_email(
                message_id=f'bot_msg_{timestamp.isoformat()}',
                timestamp=timestamp,
                from_email_address=self.email_address,
                to_email_address=user_email_address,
                email_subject=email_subject,
                email_body=email_body,
            )
            print(f"Saved response email to {user_email_address} ({email_subject})")

            # Send email
            self.email_handler.send_email(
                to_email=user_email_address,
                subject=email_subject,
                body=email_body,
            )
