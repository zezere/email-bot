import re
import json
import email
from datetime import datetime, timezone, timedelta
import hashlib
import numpy as np
from email.utils import format_datetime, parsedate_tz, parsedate_to_datetime, formatdate
from email.message import Message  # Used for type hinting


def is_valid_email_address(email_address):
    pattern = r'^[a-zA-Z0-9._%+-]+@(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    return re.match(pattern, email_address) is not None


def get_email_body(email):
    """Extract the body from an email message."""
    if email.is_multipart():
        for part in email.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode()
    return email.get_payload(decode=True).decode()


def get_message_sent_time(email):
    """Grabs "Date" field from `email` and returns a datetime object."""
    s = email.get("Date", "")
    if not s:
        print(f'Warning: email has no Date field:\n{email}')
        return datetime.now().astimezone()
    try:
        dt = parsedate_to_datetime(s)
    except ValueError as e:
        print("Warning: email Date not in RFC 2822 format, trying isoformat")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            print(f"Error in email Date field: {e}")
            return datetime.now().astimezone()
    except Exception as e:
        print(f"Error: unexpected datetime error: {e}")
        return datetime.now().astimezone()

    return dt.astimezone() if dt.tzinfo is None else dt


def datetime_to_rfc(dt):
    """Convert datetime object to RFC 2822 (email) format"""
    return formatdate(dt.timestamp(), localtime=True)


def iso_to_rfc(s: str):
    """Convert date, time from iso (SQL) to RFC 2822 (email) format."""
    dt = datetime.fromisoformat(s)
    return datetime_to_rfc(dt)


def generate_message_id(user_email_address, email_subject, email_date):
    # print(f"hashlib.md5(({user_email_address + email_subject + email_date}).encode()).hexdigest()")
    return hashlib.md5((user_email_address + email_subject + email_date).encode()).hexdigest()


def count_words(text):
    """Count words safely."""
    words = re.findall(r'\b\w+\b', text)  # Extract words safely
    return len(words)


def binary_cross_entropy(y_true, y_pred, eps=1e-15):
    y_pred = np.clip(y_pred, eps, 1 - eps)  # Avoid log(0)
    return -np.mean(y_true * np.log(y_pred) + (1 - y_true) * np.log(1 - y_pred))


def format_emails(emails, style='human_readable', bot_address='acp@startup.com'):
    """Return str composed of `emails` formatted for prompting

    Args:
        style (str): 'human'/'human_readable', 'chat', or 'json'
    """
    if style.lower() not in ['json', 'human', 'human_readable', 'chat']:
        print(f'Error in format_emails: style "{style}" not supported, using "human-readable"')

    email_history = []

    # Process all emails with common logic first
    for msg in emails:
        dt = get_message_sent_time(msg)
        formatted_date = format_datetime(dt)[:-9] if dt else "Unknown"
        sender = "assistant" if (msg.get("From", "Unknown") == bot_address) else "user"
        body = get_email_body(msg)

        if style.lower() == 'json':
            email_history.append({
                "From": sender,
                "Date": formatted_date,
                "Body": body
            })
        elif style.lower() == 'chat':
            email_history.append({
                "role": sender,
                "content": "\n".join([f"Current time: {formatted_date}", body]),
            })
        else:  # human-readable
            email_history.append(
                f'From: {sender}\n'
                f'Date: {formatted_date}\n'
                f'Content: {body}---'
            )

    # Format the final output based on style
    if style.lower() == 'json':
        # Set ensure_ascii=False to preserve emojis
        return json.dumps(email_history, indent=2, ensure_ascii=False)
    elif style.lower() == 'chat':
        return email_history
    else:
        # Return in human-readable style
        return '<Input>\n' + '\n'.join(email_history)


def get_current_user_time(user_message: Message, now: datetime = None) -> str:
    """Returns the current local time of the user.

    Analyzes the 'Date' header of an email message to determine the sender's timezone
    offset to calculate the current time in that timezone.

    Args:
        user_message: An email.message.Message object from user.

    Returns:
        A datetime object

    Raises an Error if user_message has no Date field or no valid time zone.
    """
    date_header = user_message['Date']

    # Parse the date string and extract the timezone offset in seconds from UTC
    # parsedate_tz returns a tuple: (year, month, day, hour, min, sec, wkday, yearday, isdst, offset_seconds)
    parsed_date_tuple = parsedate_tz(date_header)

    if parsed_date_tuple is None:
        raise ValueError(f"Error: Could not parse the 'Date' header: {date_header}")

    # The last element of the tuple is the timezone offset in seconds
    tz_offset_seconds = parsed_date_tuple[-1]

    if tz_offset_seconds is None:
        # Sometimes parsedate_tz succeeds but doesn't find an offset.
        # Let's check for common text zones like GMT/UTC if offset is None.
        lower_date_header = date_header.lower()
        if any(zone in lower_date_header for zone in [' gmt', ' ut', ' utc']):
            tz_offset_seconds = 0
        else:
            raise ValueError(f"Error: Could not determine timezone offset from 'Date' header: {date_header}. "
                             "No numeric offset found.")

    try:
        # Create a timezone object representing the fixed offset
        user_timezone = timezone(timedelta(seconds=tz_offset_seconds))
    except Exception as e:
        raise ValueError(f"Error creating timezone object from offset {tz_offset_seconds} seconds: {e}")

    # Get the current time in UTC (important for accurate conversion)
    if now is None:
        now_utc = datetime.now(timezone.utc)
    else:
        aware_local_now = now.astimezone()  # Makes it aware using system's idea of local time
        now_utc = aware_local_now.astimezone(timezone.utc)

    # Convert the current UTC time to the user's timezone
    now_in_user_tz = now_utc.astimezone(user_timezone)

    return now_in_user_tz
