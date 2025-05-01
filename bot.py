from datetime import datetime
import textwrap
from llm_handler import ResponseScheduler, ResponseGenerator
from scheduling import ScheduleProcessor, REMINDER_POLICIES
from utils import get_message_sent_time


class Bot:
    """
    Uses the ConversationsDB to manage conversations, schedules, and
    generate response emails for the user.

    The bot can be interrupted and restarted at any moment, its memory (state) is the database.
    """
    def __init__(self, conv_db: ConversationsDB, scheduler=None, generator=None):
        self.db = conv_db
        self.test = False
        self.track = not self.test
        self.scheduler = scheduler or ResponseScheduler()
        self.generator = generator or ResponseGenerator()
        self.running_conversations = set()  # conversation_ids handled in this bot iteration

    def analyze_conversations(self):
        """Let scheduler agent identify running conversations and new schedule agreements.

        In running conversations, the bot needs to reply asap.
        Schedules are used to trigger reminder emails.
        """
        unanalyzed_conversations = self.db.get_unanalyzed_conversations(self.track)
        if not unanalyzed_conversations:
            reason = ("At least one conversation has unfinished processes."
                      if isinstance(unanalyzed_conversations, bool)
                      else "No unanalyzed conversations found.")
            print(f"Skipping conversation analysis: {reason}")
            return

        for conversation in unanalyzed_conversations:
            conversation_id = conversation['conversation_id']
            subject = conversation['conversation_subject']
            messages = conversation['emails']
            new_schedule = None
            reply_needed = False

            result = self.scheduler.analyze_conversation(messages, now=None,
                                                         verbose=False,
                                                         DEBUG=False)

            if 'error' in result:
                print(f"schedule_response agent failed with {result['error']} "
                      f"({conversation_id}, '{subject}')")
                reply_needed = True  # fall back to default: respond to user

            elif result['response_is_due']:
                reply_needed = True

            else:
                new_schedule = result['scheduled_for']
                print(f"Result: response is NOT DUE for ({conversation_id}, '{subject}'), "
                      f"schedule set for {new_schedule.isoformat()}")

            # Future: go full probabilistic
            if hasattr(self, 'chattiness') and result['probability'] > (1 - self.chattiness):
                reply_needed = True

            self.db.update_data_after_analysis(conversation_id, new_schedule, reply_needed)
            self.running_conversations.add((conversation_id))

    def manage_running_conversations(self):
        """Generate responses in all running conversations.

        Return False if any response could not be generated or saved."""
        running_conversations = self.db.get_conversations_needing_reply()
        any_errors = False

        for conversation in running_conversations:
            conversation_id = conversation['conversation_id']
            subject = conversation['conversation_subject']
            messages = conversation['emails']
            user_name = conversation['user_name']

            # Generate response
            email_body = self.generator.generate_response(messages, user_name=user_name)

            # Handle failure
            if not email_body:
                any_errors = True
                print(f"Failed to generate response email to {user_name} ({subject})")
                print("Last message:")
                print(messages[-1])
                continue

            # Save response to database
            status = self.db.update_data_after_step2(conversation_id, email_body)
            if status:
                print(f"Saved response email to {user_name} ({subject})")
                self.running_conversations.add((conversation_id))
            else:
                print(f"Failed to save response email to {user_name} ({subject})")
                any_errors = True

        return any_errors

    def manage_reminders(self, now=None):
        """Generate reminders according to schedules and reminder policy.

        No policies will be applied if the conversation has already been processed in
        earlier steps (running conversations).
        In rare cases, a policy may analyze a conversation, which may update the schedule.

        TODO:
        - clarify what get getter returns
        - are bot emails from step2 (not sent yet) included in the emails list or separate?
        - check this case: schedule window coincides with running conversation
        - is datetime.now().astimezone() consistent with emails['date']?
        """
        conversations = self.db.get_scheduled_conversations(self.track)
        print(f"Database returned {len(conversations)} scheduled conversations.")

        processor = ScheduleProcessor()
        now = now or datetime.now().astimezone()

        for conversation in conversations:
            # Gather relevant information
            conversation_id = conversation['conversation_id']
            schedule = conversation['schedule']  # CHECK
            num_reminders_sent = conversation['num_reminders_sent']
            last_policy = conversation['last_policy']
            user_name = conversation['user_name']
            subject = conversation['conversation_subject']
            messages = conversation['emails']
            is_running = False  # TODO: this would be extra information provided by database

            if not messages:
                print(f"Error: conversation {conversation_id} ({user_name}, '{subject}') "
                      "has schedule but no messages (skipping)")
                continue

            if conversation_id in self.running_conversations or is_running:
                print(f"Conversation {conversation_id} ({user_name}, '{subject}') "
                      "is running, skipping policies")
                continue

            # Check now() is later than last email's sent time
            last_email_sent_time = get_message_sent_time(messages[-1])
            if last_email_sent_time and last_email_sent_time > now:
                print(f"Warning: Conversation {conversation_id} ({user_name}, '{subject}') "
                      f"last email was sent in the future: {last_email_sent_time} (now is {now})")

            # For policy debugging: show relevant information
            print(f"Trying up to {len(REMINDER_POLICIES)} policies in the following context:")
            print(f"    schedule: {schedule}")
            print(f"    last message:")
            print(textwrap.indent(messages[-1].as_string(), ' ' * 8))
            print(f"    current time: {now.isoformat()}\n")

            # Variant (A): try all policies, apply the first that works
            applied_policy = None
            for reminder_policy in REMINDER_POLICIES:
                processor.set_policy(reminder_policy)
                try:
                    reply_needed = processor.process_schedule(conversation_id,
                                                              schedule,
                                                              messages,
                                                              now,
                                                              num_reminders_sent,
                                                              last_policy)
                    print(f"{reminder_policy.name} was successful.")
                    applied_policy = reminder_policy.name
                    break
                except Exception as e:
                    print(f"{reminder_policy.name} failed: {e}")

            if reply_needed is False:
                # Schedule does not trigger anything
                continue

            # If the policies could not make a decision, analyze the conversation (rare)
            if reply_needed not in {True, False}:
                applied_policy = applied_policy or 'analyze'
                new_schedule = None
                reply_needed = False

                result = self.scheduler.analyze_conversation(messages, now=None,
                                                             verbose=False,
                                                             DEBUG=False)

                if 'error' in result:
                    print(f"scheduler agent failed with {result['error']}. "
                          f"Conversation: {conversation_id} ({user_name}, '{subject}')")
                    reply_needed = False  # fall back to default: don't send a reminder

                elif result['response_is_due']:
                    reply_needed = True

                else:
                    new_schedule = result['scheduled_for']
                    print(f"Result: response is NOT DUE for ({conversation_id}, '{subject}'), "
                          f"schedule set for {new_schedule.isoformat()}")

                # Future: go full probabilistic
                if hasattr(self, 'chattiness') and result['probability'] > (1 - self.chattiness):
                    reply_needed = True

                # Update database
                self.db.update_schedule(conversation_id,
                                        new_schedule,
                                        num_reminders_sent,
                                        applied_policy)

            if reply_needed:
                # Generate reminder
                email_body = self.generator.generate_response(messages,
                                                              user_name=user_name,
                                                              applied_policy=applied_policy,
                                                              num_reminders_sent=num_reminders_sent)

                # Handle failure
                if not email_body:
                    print(f"Failed to generate reminder email to {user_name} ({subject})")
                    print("Last message:")
                    print(messages[-1])
                    continue

                # Save response to database
                status = self.db.update_data_after_step2(conversation_id, email_body)
                if status:
                    print(f"Saved reminder email to {user_name} ({subject})")
                else:
                    print(f"Failed to save reminder email to {user_name} ({subject})")
