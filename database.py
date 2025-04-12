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
        SELECT m.from_email_address, m.email_subject, m.email_body, m.timestamp
        FROM messages m
        LEFT JOIN users u ON m.from_email_address = u.email_address
        WHERE (m.from_email_address = ? OR m.to_email_address = ?)
        AND m.email_subject = ?
        ORDER BY m.timestamp
    """, (user_email_address, user_email_address, email_subject))

    emails = []
    for row in c.fetchall():
        msg = EmailMessage()
        msg['From'] = row[0]
        msg['Subject'] = row[1]
        timestamp = datetime.fromisoformat(row[3])
        msg['Date'] = formatdate(timestamp.timestamp(), localtime=True)
        msg.set_content(row[2])
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


def get_user_name(user_email_address):
    """Get user_name from the users table."""
    return "Dude"


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