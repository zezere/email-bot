# TODO:
# - save_email: handle new users
# - email_exists: check also moderation database
# - new function save_moderation: store moderated emails in extra database,
# - send dev-mails if not handled automatically
# - test new function get_all_schedules()
# - test new function get_emails()

import sqlite3
from pathlib import Path
from email.message import EmailMessage
from email.utils import formatdate
from datetime import datetime

DB_PATH = Path("data/acp.db")


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    
    execute_sql(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_address TEXT NOT NULL UNIQUE,
            name TEXT
        )
        """
    )

    execute_sql(
        """
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY NOT NULL UNIQUE,
            timestamp TEXT NOT NULL, -- SQLite does not support TIMESTAMP or DATES type
            from_email_address TEXT NOT NULL,
            to_email_address TEXT NOT NULL,
            email_subject TEXT,
            email_body TEXT,
            email_sent INTEGER NOT NULL DEFAULT 0 -- SQLite does not support BOOLEAN type
        )
        """
    )

    execute_sql(
        """
        CREATE TABLE IF NOT EXISTS schedules (
            user_email_address TEXT,
            email_subject TEXT,
            scheduled_for TEXT NOT NULL, -- SQLite does not support TIMESTAMP or DATES type
            reminder_sent INTEGER NOT NULL DEFAULT 0, -- SQLite does not support BOOLEAN type
            PRIMARY KEY (user_email_address, email_subject)
        )
        """
    )


def save_email(
    message_id,
    timestamp,
    from_email_address,
    to_email_address,
    email_subject="",
    email_body="",
    email_sent=False,
):
    sql = """
        INSERT INTO messages (
            message_id, timestamp, from_email_address, to_email_address,
            email_subject, email_body, email_sent
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    execute_sql(
        sql,
        parameters=(
            message_id,
            timestamp,
            from_email_address,
            to_email_address,
            email_subject,
            email_body,
            email_sent,
        ),
    )


def email_exists(message_id):
    sql = "SELECT 1 FROM messages WHERE message_id = ?"
    result = execute_sql(sql, parameters=(message_id,), fetch='one')
    return result is not None


def get_all_schedules():
    """Gets the complete Schedule table (all rows, all fields) and returns a list of schedules with
        user_email (str),
        email_subject (str),
        timestamp (datetime),
        reminder_sent (bool).
    """
    sql = """
        SELECT user_email_address, email_subject, scheduled_for, reminder_sent
        FROM schedules
    """
    rows = execute_sql(sql, fetch='all')
    schedules = []
    for row in rows:
        dt = datetime.fromisoformat(row[2])
        schedules.append([row[0], row[1], dt, bool(row[3])])
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
    sql = """
        SELECT m.from_email_address, m.email_subject, m.email_body, m.timestamp
        FROM messages m
        LEFT JOIN users u ON m.from_email_address = u.email_address
        WHERE (m.from_email_address = ? OR m.to_email_address = ?)
        AND m.email_subject = ?
        ORDER BY m.timestamp
    """
    rows = execute_sql(sql, parameters=(user_email_address, user_email_address, email_subject), fetch='all')
    
    emails = []
    for row in rows:
        msg = EmailMessage()
        msg['From'] = row[0]
        msg['Subject'] = row[1]
        timestamp = datetime.fromisoformat(row[3])
        msg['Date'] = formatdate(timestamp.timestamp(), localtime=True)
        msg.set_content(row[2])
        emails.append(msg)
    return emails


def set_schedule_buggy(user_email_address, email_subject, scheduled_for):
    """For now, we schedule only the next check-in with the user. Hence, add row if no matching
    ("user_email_address", "email_subject") is found, else update "scheduled_for"."""
    # Try to update existing schedule
    update_sql = """
        UPDATE schedules
        SET scheduled_for = ?
        WHERE user_email_address = ? AND email_subject = ?
    """
    execute_sql(update_sql, parameters=(scheduled_for, user_email_address, email_subject))

    # If no rows were updated, insert new schedule
    insert_sql = """
        INSERT INTO schedules (user_email_address, email_subject, scheduled_for, reminder_sent)
        VALUES (?, ?, ?, ?)
    """
    execute_sql(insert_sql, parameters=(user_email_address, email_subject, scheduled_for, False))


def set_schedule(user_email_address, email_subject, scheduled_for, reminder_sent):
    """
    Schedules the next check-in.
    Uses INSERT ... ON CONFLICT DO UPDATE (upsert) to ensure only one
    schedule exists per (user_email_address, email_subject).
    If a schedule exists, it updates 'scheduled_for'.
    If no schedule exists, it inserts a new one with reminder_sent=False.
    Requires SQLite version >= 3.24.0.
    """
    # Assumes a UNIQUE constraint exists on (user_email_address, email_subject) in the 'schedules' table.
    upsert_sql = """
        INSERT INTO schedules (user_email_address, email_subject, scheduled_for, reminder_sent)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_email_address, email_subject) DO UPDATE SET
            scheduled_for = excluded.scheduled_for,
            reminder_sent = excluded.reminder_sent
    """
    execute_sql(upsert_sql, parameters=(user_email_address, email_subject, scheduled_for, reminder_sent))


def get_user_name(user_email_address):
    """Get user_name from the users table."""
    sql = "SELECT name FROM users WHERE email_address = ?"
    result = execute_sql(sql, parameters=(user_email_address,), fetch='one')
    return result[0] if result else "Dude"


def execute_sql(sql, parameters=None, fetch=None):
    """Execute SQL statement and handle database connection.
    
    Args:
        sql (str): SQL statement to execute
        parameters (tuple, optional): Parameters for SQL statement
        fetch (str, optional): Type of fetch operation: 'one', 'all', or None
    
    Returns:
        Depends on fetch parameter:
        - 'one': Returns single row
        - 'all': Returns all rows
        - None: Returns None (for INSERT, UPDATE, DELETE operations)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            c = conn.cursor()
            if parameters:
                c.execute(sql, parameters)
            else:
                c.execute(sql)
                
            if fetch == 'one':
                result = c.fetchone()
            elif fetch == 'all':
                result = c.fetchall()
            else:
                result = None
                
            conn.commit()
            return result
        except sqlite3.Error as e:
            print(f"Database error: {str(e)}")
            print(f"Failed SQL: {sql}")
            if parameters:
                print(f"Parameters: {parameters}")
            conn.rollback()
            raise
        finally:
            conn.close()
    except sqlite3.Error as e:
        print(f"Connection error: {str(e)}")
        print(f"Database path: {DB_PATH}")
        raise