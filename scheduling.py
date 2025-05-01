"""
The policies in this module define scenarios in which they apply by making
various assertions. If these assertions are all fulfilled, the policy takes
action.

A policy considers any relevant information from past messages, current time,
and the current schedule.

It returns True or False when a deterministic decision can be made, otherwise
leaves it to the agents to decide what to do.

Earlier version:
- schedule: (user, subject, due_time, reminder_sent)
- and reminder_sent: bool
is replaced by
- conversation_id: int
- schedule: datetime
- num_reminders_sent: int
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from utils import get_message_sent_time


# Abstract Strategy (Policy) class
class ReminderPolicy(ABC):
    def __init__(self) -> None:
        super().__init__()
        self.name = self.__class__.__name__

    @abstractmethod
    def process_schedule(self,
                         conversation_id: int,
                         schedule: datetime,
                         messages: list,
                         now: datetime,
                         num_reminders_sent: int,
                         last_policy: str) -> bool | str:
        """Process a single schedule according to this policy."""
        pass


class DefaultPolicy(ReminderPolicy):
    def process_schedule(self,
                         conversation_id: int,
                         schedule: datetime,
                         messages: list,
                         now: datetime,
                         num_reminders_sent: int,
                         last_policy: str) -> bool | str:
        """Respond now. Always works."""
        return True


class AskAgentPolicy(ReminderPolicy):
    def process_schedule(self,
                         conversation_id: int,
                         schedule: datetime,
                         messages: list,
                         now: datetime,
                         num_reminders_sent: int,
                         last_policy: str) -> bool | str:
        """Leave it to the scheduler agent to decide.

        At least, works for me 😉"""
        return 'maybe'


class EarlyReminderPolicy(ReminderPolicy):
    def __init__(self, hour: int = 9):
        """Set the reminder time (hour in user's time zone) on scheduled day."""
        super().__init__()
        self.reminder_time = int(hour)

    def process_schedule(self,
                         conversation_id: int,
                         schedule: datetime,
                         messages: list,
                         now: datetime,
                         num_reminders_sent: int,
                         last_policy: str) -> bool | str:
        """If the schedule is for today, send a reminder at reminder_time."""

        # Assumptions
        assert schedule.date() == now.date(), "scheduled time is not today"
        assert num_reminders_sent == 0, "first reminder already sent"

        # Action
        now_in_user_tz = now.astimezone(get_user_time_zone(messages))
        response_is_due = now_in_user_tz.hour >= self.reminder_time

        return response_is_due


class SecondReminderPolicy(ReminderPolicy):
    def __init__(self, waiting_time: timedelta = timedelta(hours=3)):
        """Set how long to wait for the user's check-in before sending a second reminder."""
        super().__init__()
        self.waiting_time = waiting_time

    def process_schedule(self,
                         conversation_id: int,
                         schedule: datetime,
                         messages: list,
                         now: datetime,
                         num_reminders_sent: int,
                         last_policy: str) -> bool | str:
        """After waiting_time, a second reminder is due."""

        # Assumptions
        assert now - schedule >= self.waiting_time, "continue waiting for user"
        assert num_reminders_sent < 2, "second reminder already sent"

        # Action
        return True


class LateReminderPolicy(ReminderPolicy):
    def __init__(self, waiting_time: timedelta = timedelta(hours=1)):
        """Set how long to wait for the user's check-in before sending a first reminder."""
        super().__init__()
        self.waiting_time = waiting_time

    def process_schedule(self,
                         conversation_id: int,
                         schedule: datetime,
                         messages: list,
                         now: datetime,
                         num_reminders_sent: int,
                         last_policy: str) -> bool | str:
        """After waiting_time, a first reminder is due."""

        # Assumptions
        assert now - schedule >= self.waiting_time, "continue waiting for user"
        assert num_reminders_sent == 0, "first reminder already sent"

        # Action
        return True


class WaitForSchedulePolicy(ReminderPolicy):
    def __init__(self, max_delay: timedelta = timedelta(hours=6)):
        """Set the max time delay for a bot response before giving up on unscheduled response."""
        super().__init__()
        self.max_delay = max_delay

    def process_schedule(self,
                         conversation_id: int,
                         schedule: datetime,
                         messages: list,
                         now: datetime,
                         num_reminders_sent: int,
                         last_policy: str) -> bool | str:
        """Avoid untimely response.

        If already max_delay time has passed since last message, wait for schedule or
        (if nothing scheduled ahead) ask agent.
        """
        last_contact = get_message_sent_time(messages[-1])
        hours_past = self.max_delay.seconds // 3600
        schedule_ahead = (schedule.day - now.day) > 0

        # Assumptions
        assert (now - last_contact) > self.max_delay, (
            f"less than {hours_past} hours since last contact, not too late to respond now")

        # Action
        return False if schedule_ahead else 'ask agent'


class BestPolicy(ReminderPolicy):
    def process_schedule(self,
                         conversation_id: int,
                         schedule: datetime,
                         messages: list,
                         now: datetime,
                         num_reminders_sent: int,
                         last_policy: str) -> bool | str:
        raise NotImplementedError('not implemented')


# The bot will try these policies in this order:
REMINDER_POLICIES = [
    BestPolicy(),
    WaitForSchedulePolicy(),
    EarlyReminderPolicy(),
    LateReminderPolicy(),
    SecondReminderPolicy(),
    AskAgentPolicy(),
    DefaultPolicy()]


class ScheduleProcessor:
    def __init__(self, policy: ReminderPolicy = None):
        self.policy = policy or DefaultPolicy()

    def set_policy(self, policy: ReminderPolicy):
        """Change the policy at runtime."""
        self.policy = policy

    def process_schedule(self, *args, **kwargs):
        """Process schedule using the current policy."""
        return self.policy.process_schedule(*args, **kwargs)


def get_user_messages(messages: list) -> list:
    return [msg for msg in messages if msg["role"] == "user"]


def get_bot_messages(messages: list) -> list:
    return [msg for msg in messages if msg["role"] == "assistant"]


def get_user_time_zone(messages: list) -> str:
    user_messages = get_user_messages(messages)
    timezones = [msg["date"].tzinfo for msg in user_messages]
    return timezones[-1] if timezones else None
