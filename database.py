import sqlite3
from pathlib import Path

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
            sent_at TIMESTAMP
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


def save_email(message_id, sender_name, sender_email, subject, body, sent_at):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO emails (message_id, sender_name, sender_email, subject, body, sent_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (message_id, sender_name, sender_email, subject, body, sent_at),
    )
    conn.commit()
    conn.close()


def email_exists(message_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM emails WHERE message_id = ?", (message_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists
