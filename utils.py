import re
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
    except Exception as e:
        print(f"ERROR: Date not in iso format: {s}")
    return dt


def count_words(text):
    """Count words safely."""
    words = re.findall(r'\b\w+\b', text)  # Extract words safely
    return len(words)


def binary_cross_entropy(y_true, y_pred, eps=1e-15):
    y_pred = np.clip(y_pred, eps, 1 - eps)  # Avoid log(0)
    return -np.mean(y_true * np.log(y_pred) + (1 - y_true) * np.log(1 - y_pred))
