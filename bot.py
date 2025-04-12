from time import perf_counter
from datetime import datetime
import textwrap
from database import save_email, save_moderation, email_exists, get_all_schedules, get_emails, set_schedule
from email_handler import EmailHandler
from llm_handler import LLMHandler
import email.utils
from scheduling import ScheduleProcessor, REMINDER_POLICIES, choose_policy
from utils import is_valid_email_address, get_email_body, get_message_sent_time, generate_message_id


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
        self.test = False
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
            to_email_address = email_msg.get("To", "")
            subject = email_msg.get("Subject", "")
            body = get_email_body(email_msg)
            sent_at = get_message_sent_time(email_msg)

            # Validate sender_email address
            print(f"Validating new email {message_id} ({sender_email}, '{subject}', {sent_at.isoformat()})")
            if not is_valid_email_address(sender_email):
                print(f"    invalid email address: {sender_email[:50]}")
                continue

            # Quickly validate and block spam
            # In test mode, don't validate emails from myself
            if self.test and (sender_email == self.email_address):
                response, reasoning = 'pass', 'test email from myself'
            else:
                response, reasoning = self.llm_handler.validate_email(sender_email, subject, body)
            if response == "pass":
                pass
            elif response == "block":
                print(f"Blocked email {message_id} from {sender_email} (spam)")
                continue
            else:
                print("Validation skipped: LLM did not follow instructions")
                if self.test:
                    print(f"Response:\n{response}, {reasoning}\n")

            # Moderate the email content
            if self.test:
                # skip moderation
                is_appropriate, moderation_result = True, 'APPROPRIATE'
            else:
                is_appropriate, moderation_result = self.llm_handler.moderate_email(body)
            if not is_appropriate:
                print(f"Moderation result for {message_id}: {moderation_result}")
                save_moderation(
                    message_id=message_id,
                    timestamp=sent_at,
                    sender_name=sender_name,
                    from_email_address=sender_email,
                    to_email_address=to_email_address or self.email_address,
                    email_subject=subject,
                    email_body=body,
                    email_sent=True,
                )
                print(f"Saved new email from {sender_email} ({subject}). "
                      f"Delay: {(datetime.now().astimezone() - sent_at).seconds / 60:.1f} min")

            # Save email information to database
            save_email(
                message_id=message_id,
                timestamp=sent_at,
                from_email_address=sender_email,
                to_email_address=to_email_address or self.email_address,
                email_subject=subject,
                email_body=body,
                email_sent=True,
            )
            print(f"Saved new email: {message_id} from {sender_email} ({subject})")

            # Agent needs to decide: respond or set/update schedule?
            if sender_email == self.email_address:
                if not self.test:
                    print(f"Error: received email from myself:\n{email_msg}")
            else:
                if self.test:
                    print(f"sender: {sender_email} is not bot: {self.email_address}, adding to ask_agent.")
                self.ask_agent.add((sender_email, subject))

        print(f"Processing new emails completed in {perf_counter() - start_time:.1f} sec.")

    def process_schedules(self):
        """Update active_conversations according to schedules and reminder policy."""
        schedules = get_all_schedules()
        print(f"Database returned {len(schedules)} scheduled conversations.")

        processor = ScheduleProcessor()

        for schedule in schedules:
            # Gather relevant information
            user, subject, due_time, reminder_sent = schedule
            just_got_user_mail = (user, subject) in self.active_conversations
            messages = get_emails(user, subject)
            if not messages:
                print(f"Error: conversation ({user, subject}) has schedule but no messages (skipping)")
                continue
            now = datetime.now().astimezone()

            # For policy debugging: show relevant information
            print(f"Trying up to {len(REMINDER_POLICIES)} policies in the following context:")
            print(f"    schedule: {schedule}")
            print(f"    last message:")
            print(textwrap.indent(messages[-1].as_string(), ' ' * 8))
            print(f"    current time: {now.isoformat()}\n")

            # Variant (A): try all policies, apply the first that works
            for reminder_policy in REMINDER_POLICIES:
                processor.set_policy(reminder_policy)
                try:
                    response_is_due = processor.process_schedule(schedule, 
                                                                 just_got_user_mail,
                                                                 messages, 
                                                                 now)
                    print(f"{reminder_policy.name} was successful.")
                    break
                except Exception as e:
                    print(f"{reminder_policy.name} failed: {e}")

            # Variant (B): use a sophisticated choose_policy function
            # reminder_policy = choose_policy(schedule, just_got_user_mail, messages, now)
            # processor.set_policy(reminder_policy)
            # response_is_due = processor.process_schedule(schedule, just_got_user_mail,
            #                                              messages, now)

            if self.test:
                assert isinstance(user, str)  # DEBUG
                assert user != self.email_address, f'user from schedule was bot!!!'  # DEBUG

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

            if self.test:
                assert isinstance(user_email_address, str)  # DEBUG
                assert user_email_address != self.email_address, f'user_email_address from ask_agent was bot!!!'  # DEBUG

            if 'error' in result:
                print(f"schedule_response agent failed with {result['error']} "
                      f"({user_email_address}, '{email_subject}')")
                # On error, fall back to default: respond to user
                self.active_conversations.add((user_email_address, email_subject))
            elif result['response_is_due']:
                self.active_conversations.add((user_email_address, email_subject))
                print(f"Result: response is DUE, added  ({user_email_address}, '{email_subject}') "
                      "to active_conversations.")
            else:
                scheduled_for = result['scheduled_for']
                set_schedule(user_email_address, email_subject, scheduled_for)
                print(f"Result: response is NOT DUE for ({user_email_address}, '{email_subject}'), "
                      f"schedule set for {scheduled_for.isoformat()}")

            # Future: go full probabilistic
            if hasattr(self, 'chattiness') and result['probability'] > (1 - self.chattiness):
                self.active_conversations.add((user_email_address, email_subject))

    def generate_responses(self):
        """Reply in all active_conversations."""
        llm_handler = LLMHandler()

        for user_email_address, email_subject in self.active_conversations:
            messages = get_emails(user_email_address, email_subject)

            email_body = llm_handler.generate_response(messages, bot_address=self.email_address)

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
                message_id=generate_message_id(user_email_address, email_subject, timestamp.isoformat()),
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
