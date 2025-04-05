import re
import json
import email
from datetime import datetime
import numpy as np


def get_email_body(email):
    """Extract the body from an email message."""
    if email.is_multipart():
        for part in email.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode()
    return email.get_payload(decode=True).decode()


def get_message_sent_time(email, debug=True):
    """Grabs "Date" field from `email` and returns a datetime object."""
    s = email.get("Date", "")
    if debug:
        assert s, f'email has no Date: {email}'
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        print(f"ERROR in email Date field: {e}")
        return datetime.now()
    except Exception as e:
        print(f"ERROR: unexpected datetime error: {e}")
        return datetime.now()
    return dt


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
        style (str): 'human'/'human_readable' or 'json'
    """
    if style.lower() not in ['json', 'human', 'human_readable']:
        raise ValueError(f"format_emails: style {style} not supported")

    email_history = []

    # Process all emails with common logic first
    for msg in emails:
        dt = get_message_sent_time(msg)
        formatted_date = email.utils.format_datetime(dt)[:-9] if dt else "Unknown"
        sender = "assistant" if (msg.get("From", "Unknown") == bot_address) else "user"
        body = get_email_body(msg)

        if style.lower() == 'json':
            email_history.append({
                "From": sender,
                "Date": formatted_date,
                "Body": body
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
    else:
        # Return in human-readable style
        return '<Input>\n' + '\n'.join(email_history)
