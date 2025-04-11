"""
The policies in this module define scenarios in which they apply by making
various assertions. If these assertions are all fulfilled, the policy takes
action.

A policy considers any relevant information from past messages, current time,
and the current schedule.

It returns True or False when a deterministic decision can be made, otherwise
leaves it to the agents to decide what to do.
"""

from abc import ABC, abstractmethod
from typing import List, Union
from datetime import datetime, timedelta
from utils import get_current_user_time


# Abstract Strategy (Policy) class
class ReminderPolicy(ABC):
    @abstractmethod
    def process_schedule(self,
                         schedule: List[Union[str, datetime, bool, int]],
                         just_got_user_mail: bool,
                         messages: list,
                         now: datetime) -> bool | str:
        """Process a single schedule according to this policy."""
        pass


class DefaultPolicy(ReminderPolicy):
    def process_schedule(self,
                         schedule: List[Union[str, datetime, bool, int]],
                         just_got_user_mail: bool,
                         messages: list,
                         now: datetime) -> bool | str:
        """Respond now. Always works."""
        return True


class AskAgentPolicy(ReminderPolicy):
    def process_schedule(self,
                         schedule: List[Union[str, datetime, bool, int]],
                         just_got_user_mail: bool,
                         messages: list,
                         now: datetime) -> bool | str:
        """Leave it to the schedule_response agent to decide.

        At least, works for me 😉"""
        return 'maybe'


class EarlyReminderPolicy(ReminderPolicy):
    def __init__(self):
        self.reminder_time = 9

    def set_reminder_time(self, hour: int):
        """Set the reminder time (hour in user's time zone) on scheduled day."""
        self.reminder_time = int(hour)

    def process_schedule(self,
                         schedule: List[Union[str, datetime, bool, int]],
                         just_got_user_mail: bool,
                         messages: list,
                         now: datetime) -> bool | str:
        """If the schedule is for today, send a reminder at reminder_time."""
        user, subject, due_time, reminder_sent = schedule

        # Infer users's timezone from last or first message
        user_message = messages[-1] if just_got_user_mail else messages[0]
        sender_email = user_message.get("From")

        # Assumptions
        assert due_time.date() == now.date(), "scheduled time is not today"
        assert sender_email == user, f"first/last message not from user but {sender_email}"

        # Action
        now_in_user_tz = get_current_user_time(user_message, now)
        response_is_due = now_in_user_tz.hour >= self.reminder_time

        return response_is_due


class SecondReminderPolicy(ReminderPolicy):
    def __init__(self):
        self.waiting_time = timedelta(hours=3)

    def set_waiting_time(self, delta: timedelta):
        """Set how long to wait for the user's check-in before sending a second reminder."""
        self.waiting_time = delta

    def process_schedule(self,
                         schedule: List[Union[str, datetime, bool, int]],
                         just_got_user_mail: bool,
                         messages: list,
                         now: datetime) -> bool | str:
        """After waiting_time, a second reminder is due."""
        user, subject, due_time, reminder_sent = schedule

        # Assumptions
        assert not just_got_user_mail, "user already checked in."
        assert now - due_time >= self.waiting_time, "continue waiting for user"
        if isinstance(reminder_sent, int):
            assert reminder_sent < 2, "second reminder already sent"

        # Action
        return True


class LateReminderPolicy(ReminderPolicy):
    def __init__(self):
        self.waiting_time = timedelta(hours=1)

    def set_waiting_time(self, delta: timedelta):
        """Set how long to wait for the user's check-in before sending a first reminder."""
        self.waiting_time = delta

    def process_schedule(self,
                         schedule: List[Union[str, datetime, bool, int]],
                         just_got_user_mail: bool,
                         messages: list,
                         now: datetime) -> bool | str:
        """After waiting_time, a first reminder is due."""
        user, subject, due_time, reminder_sent = schedule

        # Assumptions
        assert not just_got_user_mail, "user already checked in."
        assert now - due_time >= self.waiting_time, "continue waiting for user"
        assert not reminder_sent, "first reminder already sent"

        # Action
        return True


class WaitForSchedulePolicy(ReminderPolicy):
    def __init__(self):
        self.max_delay = timedelta(hours=6)

    def set_max_delay(self, max_delay: timedelta):
        """Set the max time delay for a bot response before giving up on unscheduled response."""
        self.max_delay = max_delay

    def process_schedule(self,
                         schedule: List[Union[str, datetime, bool, int]],
                         just_got_user_mail: bool,
                         messages: list,
                         now: datetime) -> bool | str:
        """Avoid untimely response.

        If already max_delay time has passed since last message, wait for schedule or
        (if nothing scheduled ahead) ask agent.
        """
        user, subject, due_time, reminder_sent = schedule
        last_contact = messages[-1]["Date"]
        hours_past = self.max_delay.seconds // 3600
        schedule_ahead = (due_time.day - now.day) > 0

        # Assumptions
        assert not just_got_user_mail, "don't wait, just_got_user_mail!"
        assert (now - last_contact) > self.max_delay, (
            f"less than {hours_past} hours since last contact, not too late to respond now")

        # Action
        return False if schedule_ahead else 'ask agent'


class ImmediateResponsePolicy(ReminderPolicy):
    def process_schedule(self,
                         schedule: List[Union[str, datetime, bool, int]],
                         just_got_user_mail: bool,
                         messages: list,
                         now: datetime) -> bool | str:
        """After receiving a user email, the schedule_response agent must decide."""
        # Assumptions
        assert just_got_user_mail, 'no new user emails'

        # Action
        return 'ask agent'


class BestPolicy(ReminderPolicy):
    def process_schedule(self,
                         schedule: List[Union[str, datetime, bool, int]],
                         just_got_user_mail: bool,
                         messages: list,
                         now: datetime) -> bool | str:
        raise NotImplementedError


# The bot will try these policies in this order:
REMINDER_POLICIES = [
    BestPolicy(),
    ImmediateResponsePolicy(),
    WaitForSchedulePolicy(),
    EarlyReminderPolicy(),
    LateReminderPolicy(),
    SecondReminderPolicy(),
    AskAgentPolicy(),
    DefaultPolicy()]


def choose_policy(schedule, just_got_user_mail, messages, now):
    raise NotImplementedError("Use Variant (A) for now!")


class ScheduleProcessor:
    def __init__(self, policy: ReminderPolicy = None):
        self.policy = policy or DefaultPolicy()

    def set_policy(self, policy: ReminderPolicy):
        """Change the policy at runtime."""
        self.policy = policy

    def process_schedule(self, *args, **kwargs):
        """Process schedule using the current policy."""
        return self.policy.process_schedule(*args, **kwargs)
