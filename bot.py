from datetime import datetime
import textwrap
from utils import wrap_indent
from llm_handler import ResponseScheduler, ResponseGenerator
from scheduling import ScheduleProcessor, REMINDER_POLICIES


class Bot:
    """
    Uses the ConversationsDB to manage conversations, schedules, and
    generate response emails for the user.

    The bot can be interrupted and restarted at any moment, its memory (state) is the database.
    """
    def __init__(self, conv_db, scheduler=None, generator=None, test=False):
        self.db = conv_db
        self.test = test
        self.track = True  # not self.test: update_data_after_analysis fails if track=False
        self.scheduler = scheduler or ResponseScheduler()
        self.generator = generator or ResponseGenerator()
        self.running_conversations = set()  # conversation_ids handled in this bot iteration

    def analyze_conversations(self):
        """Let scheduler agent identify running conversations and new schedule agreements.

        In running conversations, the bot needs to reply asap.
        Schedules are used to trigger reminder emails.
        """
        unanalyzed_conversations = self.db.get_unanalyzed_conversations(self.track)
        any_errors = False

        if not unanalyzed_conversations:
            # False or empty?
            reason = ("At least one conversation has unfinished processes."
                      if isinstance(unanalyzed_conversations, bool)
                      else "No unanalyzed conversations found.")
            print(f"Step 1: Skipping conversation analysis: {reason}")
            return  # TODO: should the bot behave differently if False? Is this redundant with all_processes_completed?

        if self.test:
            print(f"Step 1: Database returned {len(unanalyzed_conversations)} conversations for analysis...")

        for conversation in unanalyzed_conversations:
            conversation_id = conversation['conversation_id']
            subject = conversation['conversation_subject']
            messages = conversation['emails']
            new_schedule = None
            reply_needed = False

            if self.test:
                print(f"\nConversation {conversation_id} ({subject}, {len(messages)} messages, last from {messages[-1]['role']})")

            result = self.scheduler.analyze_conversation(messages, now=None, debug_level=0)

            if 'error' in result:
                print(f"schedule_response agent failed with {result['error']} "
                      f"({conversation_id}, '{subject}')")
                reply_needed = True  # fall back to default: respond to user

            elif result['response_is_due']:
                reply_needed = True
                if self.test:
                    print("Result: Reply needed.")

            else:
                new_schedule = result['scheduled_for']
                if self.test:
                    print(f"Result: No reply needed. Setting schedule for {new_schedule.isoformat()}")

            # Future: go full probabilistic
            if hasattr(self, 'chattiness') and result['probability'] > (1 - self.chattiness):
                reply_needed = True

            update_complete = self.db.update_data_after_analysis(conversation_id, new_schedule, reply_needed)
            if update_complete:
                self.running_conversations.add((conversation_id))
            else:
                print(f"Failed to update data after analysis for ({conversation_id}, '{subject}')")
                any_errors = True

        return any_errors

    def manage_running_conversations(self):
        """Generate responses for all running conversations.

        Return False if any response could not be generated or saved."""
        running_conversations = self.db.get_conversations_needing_reply()
        any_errors = False

        if not running_conversations:
            print("\nStep 2: Database returned no running conversations.")
            return any_errors
        else:
            print(f"\nStep 2: Database returned {len(running_conversations)} running conversations, generating responses...")

        for conversation in running_conversations:
            conversation_id = conversation['conversation_id']
            subject = conversation['conversation_subject']
            messages = conversation['emails']
            user_name = conversation['user_name']

            # Generate response
            print(f"\nConversation {conversation_id} ({user_name}, '{subject}', {len(messages)} messages)")
            email_body = self.generator.generate_response(messages, user_name=user_name)

            # Handle failure
            if not email_body:
                any_errors = True
                print(f"Failed to generate response email to {user_name} ({subject})")
                print("Last message:")
                print(str(messages[-1]))
                continue

            if self.test:
                print("Generated response:")
                print(wrap_indent(email_body, width=80, indentation=8))

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
        print(f"\nStep 3: Database returned {len(conversations)} scheduled conversations.")

        processor = ScheduleProcessor()
        now = now or datetime.now().astimezone()

        for conversation in conversations:
            # Gather relevant information
            conversation_id = conversation['conversation_id']
            schedule = conversation['schedule'].astimezone()  # TODO: call timezone already in conversations_db
            num_reminders_sent = conversation['num_reminders']
            last_policy = conversation['last_policy']
            user_name = conversation['user_name']
            subject = conversation['conversation_subject']
            messages = conversation['emails']
            is_running = False  # TODO: this would be extra information provided by database

            if not messages:
                print(f"\nError: conversation {conversation_id} ({user_name}, '{subject}') "
                      "has schedule but no messages (skipping)")
                continue

            if conversation_id in self.running_conversations or is_running:
                print(f"\nConversation {conversation_id} ({user_name}, '{subject}') "
                      "is running, skipping policies")
                continue

            # Check now() is later than last email's sent time
            last_email_sent_time = messages[-1]['sorting_timestamp']
            if last_email_sent_time and last_email_sent_time > now:
                print(f"\nWarning: Conversation {conversation_id} ({user_name}, '{subject}') "
                      f"last email was sent in the future: {last_email_sent_time} (now is {now})")

            # For policy debugging: show relevant information
            print(f"\nConversation {conversation_id} ({user_name}, '{subject}'): "
                  f"Trying up to {len(REMINDER_POLICIES)} policies. Context:")
            print(f"    schedule:     {schedule}")
            print(f"    current time: {now.isoformat()}")
            print(f"    last message:")  # noqa F541
            print(textwrap.indent(str(messages[-1]), ' ' * 8))

            # Try all policies, apply the first that works
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
                    print(f"{reminder_policy.name} was successful (reply_needed: {reply_needed}).")
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

                result = self.scheduler.analyze_conversation(messages, now=None, debug_level=0)

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
                                                              applied_policy=applied_policy)

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
                    # return  # Stop processing reminders on database error
