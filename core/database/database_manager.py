import sqlite3
import os
import json
from pathlib import Path
from typing import List, Optional

# TODO for the DevOps team: ps_list should be in a separate database
# TODO for the DevOps team: and email worker jobs also separately (debatable)


class DatabaseManager:
    def __init__(self, db_name: str):
        # Get the project root directory (2 levels up from this file)
        self.root_dir = Path(__file__).parent.parent.parent
        self.data_dir = self.root_dir / "data"
        self.data_dir.mkdir(exist_ok=True)  # Create data directory if it doesn't exist
        self.db_path = self.data_dir / db_name

        # Initialize database with tables if they don't exist
        self._initialize_database()

    def _initialize_database(self) -> None:
        """Initialize database and create tables if they don't exist."""
        create_tables_queries = [
            # Business logic tables
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                name TEXT
            )""",
            """
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                date TEXT NOT NULL,
                from_email TEXT NOT NULL,
                to_email TEXT NOT NULL,
                subject TEXT,
                body TEXT,
                conversation_id INTEGER,
                analyzed BOOLEAN NOT NULL DEFAULT 0,
                processed BOOLEAN NOT NULL DEFAULT 0,
                headers TEXT,
                sorting_timestamp TEXT
            )""",
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                conversation_subject TEXT,
                reply_needed BOOLEAN NOT NULL DEFAULT 0
            )""",
            """
            CREATE TABLE IF NOT EXISTS prepared_replies(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                reply_subject TEXT,
                reply_message TEXT,
                timestamp TEXT NOT NULL,
                awareness_timestamp TEXT
            )""",
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                conversation_id INTEGER NOT NULL,
                num_reminders INTEGER,
                last_policy TEXT
            )""",
            # System tables
            """
            CREATE TABLE IF NOT EXISTS ps_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                source TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT
            )""",
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL
            )""",
            """
            CREATE TABLE IF NOT EXISTS mail_crontab (
                id INTEGER PRIMARY KEY AUTOINCREMENT
            )
            """,
        ]

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            for query in create_tables_queries:
                cursor.execute(query)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Database error: {str(e)}")
            raise e
        finally:
            conn.close()

    def execute_query(
        self, query: str, params: Optional[tuple] = None
    ) -> List[sqlite3.Row]:
        """Execute a query and return the results."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionary-like objects
        cursor = conn.cursor()

        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            result = cursor.fetchall()  # Fetch results before closing connection
            conn.commit()
            return result
        except Exception as e:
            conn.rollback()
            print(f"Database error: {str(e)}")
            raise e
        finally:
            conn.close()

    # TODO (later): get rid of "?" to prevent SQL injection
    # TODO (later): add possibility to execute inserts one by one
    def insert_data(self, table_name: str, data: dict) -> None:
        """Insert one row into a table."""
        query = f"INSERT INTO {table_name} ({', '.join(data.keys())}) VALUES ({', '.join(['?' for _ in data])})"
        self.execute_query(query, tuple(data.values()))

    # TODO (later): get rid of "?" to prevent SQL injection
    # TODO (later): add possibility to execute updates one by one
    def update_data(self, table_name: str, data: dict, condition: str) -> None:
        """Update one row in a table."""
        query = f"UPDATE {table_name} SET {', '.join([f'{k} = ?' for k in data.keys()])} WHERE {condition}"
        self.execute_query(query, tuple(data.values()))

    def _insert_test_data(
        self,
        emails_file_name: str,
        conversations_file_name: str,
        schedules_file_name: str,
        users_file_name: str,
    ):
        if emails_file_name:
            with open(self.data_dir / emails_file_name, "r", encoding="utf-8") as f:
                test_emails = json.load(f)

        if conversations_file_name:
            with open(
                self.data_dir / conversations_file_name, "r", encoding="utf-8"
            ) as f:
                test_conversations = json.load(f)

        if schedules_file_name:
            with open(self.data_dir / schedules_file_name, "r", encoding="utf-8") as f:
                test_schedules = json.load(f)

        if users_file_name:
            with open(self.data_dir / users_file_name, "r", encoding="utf-8") as f:
                test_users = json.load(f)

        for email in test_emails:
            self.insert_data("emails", email)

        for conversation in test_conversations:
            self.insert_data("conversations", conversation)

        for user in test_users:
            self.insert_data("users", user)

        for schedule in test_schedules:
            self.insert_data("schedules", schedule)


# ===================================================================
# Section for testing how database manager works - NOT FOR PRODUCTION
# ===================================================================
if __name__ == "__main__":

    db_manager = DatabaseManager("test.db")
    db_manager._insert_test_data(
        emails_file_name="test_emails.json",
        conversations_file_name="test_conversations.json",
        schedules_file_name="test_schedules.json",
        users_file_name="test_users.json",
    )
    # ================================
    # How to use Row object
    # ================================

    # print("\nAs dictionary:", dict(row))  # Print as dictionary
    # print("By column name:", row['name'])  # Access by column name
    # print("By index:", row[0])  # Access by index
    # print("Column names:", row.keys())  # Print all column names
