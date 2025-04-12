# TODO:
# - save_email: handle new users
# - email_exists: check also moderation database
# - new function save_moderation: store moderated emails in extra database,
#   send dev-mails if not handled automatically
# - test new function get_all_schedules()
# - test new function get_emails()

import sqlite3
from pathlib import Path
from email.message import EmailMessage
from email.utils import formatdate
from datetime import datetime

DB_PATH = Path("data/apai.db")


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            goal TEXT,
            last_contact TIMESTAMP,
            status TEXT
        )
    """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS emails (
            message_id TEXT PRIMARY KEY,
            sender_name TEXT,
            sender_email TEXT,
            subject TEXT,
            body TEXT,
            sent_at TIMESTAMP,
            is_appropriate BOOLEAN,
            moderation_reason TEXT
        )
    """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY,
            timestamp TIMESTAMP,
            from_email_address TEXT,
            to_email_address TEXT,
            email_subject TEXT,
            email_body TEXT,
            email_sent BOOLEAN
        )
    """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS schedules (
            user_email_address TEXT,
            email_subject TEXT,
            scheduled_for TIMESTAMP,
            reminder_sent BOOLEAN,
            PRIMARY KEY (user_email_address, email_subject)
        )
    """
    )

    conn.commit()
    conn.close()


def get_user(email):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = c.fetchone()
    conn.close()
    return user


def add_user(email, goal):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO users (email, goal, status) VALUES (?, ?, ?)",
        (email, goal, "active"),
    )
    conn.commit()
    conn.close()


def save_email(
    message_id,
    timestamp,
    from_email_address,
    to_email_address,
    email_subject,
    email_body,
    email_sent=False,
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO messages (
            message_id, timestamp, from_email_address, to_email_address,
            email_subject, email_body, email_sent
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message_id,
            timestamp,
            from_email_address,
            to_email_address,
            email_subject,
            email_body,
            email_sent,
        ),
    )
    conn.commit()
    conn.close()


def save_moderation(
    message_id,
    timestamp,
    sender_name,
    from_email_address,
    to_email_address,
    email_subject,
    email_body,
    moderation_reason,
):
    pass


def email_exists(message_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM messages WHERE message_id = ?", (message_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists


def get_all_schedules():
    """Gets the complete Schedule table (all rows, all fields) and returns a list of schedules with
        user_email (str),
        email_subject (str),
        timestamp (datetime),
        reminder_sent (bool).
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT user_email_address, email_subject, scheduled_for, reminder_sent
        FROM schedules
    """)
    schedules = []
    for row in c.fetchall():
        dt = datetime.fromisoformat(row[2])
        schedules.append([row[0], row[1], dt, bool(row[3])])
    conn.close()
    return schedules


def get_emails(user_email_address, email_subject):
    """Selects all messages where
    ("from_email_address" OR "to_email_address" matches user_email_address) AND "email_subject"
    matches email_subject.
    Returns a list of emails with
        "from_email_address",
        [optional: user.name to that from_email_address],
        email_subject,
        email_body,
        timestamp.
    The list should be sorted by those timestamps.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # First get the sender name from users table
    c.execute("""
        SELECT m.from_email_address, u.goal, m.email_subject, m.email_body, m.timestamp
        FROM messages m
        LEFT JOIN users u ON m.from_email_address = u.email
        WHERE (m.from_email_address = ? OR m.to_email_address = ?)
        AND m.email_subject = ?
        ORDER BY m.timestamp
    """, (user_email_address, user_email_address, email_subject))

    emails = []
    for row in c.fetchall():
        msg = EmailMessage()
        msg['From'] = row[0]
        msg['Subject'] = row[2]
        timestamp = datetime.fromisoformat(row[4])
        msg['Date'] = formatdate(timestamp.timestamp(), localtime=True)
        msg.set_content(row[3])
        emails.append(msg)

    conn.close()
    return emails


def set_schedule(user_email_address, email_subject, scheduled_for):
    """For now, we schedule only the next check-in with the user. Hence, add row if no matching
    ("user_email_address", "email_subject") is found, else update "scheduled_for"."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Try to update existing schedule
    c.execute("""
        UPDATE schedules
        SET scheduled_for = ?
        WHERE user_email_address = ? AND email_subject = ?
    """, (scheduled_for, user_email_address, email_subject))

    # If no rows were updated, insert new schedule
    if c.rowcount == 0:
        c.execute("""
            INSERT INTO schedules (user_email_address, email_subject, scheduled_for, reminder_sent)
            VALUES (?, ?, ?, ?)
        """, (user_email_address, email_subject, scheduled_for, False))

    conn.commit()
    conn.close()
