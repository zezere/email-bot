import sqlite3
import os
from pathlib import Path
from typing import List, Optional


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
                headers TEXT
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
                timestamp TEXT NOT NULL
            )""",
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                conversation_id INTEGER NOT NULL
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

    def insert_data(self, table_name: str, data: dict) -> None:
        """Insert one row into a table."""
        query = f"INSERT INTO {table_name} ({', '.join(data.keys())}) VALUES ({', '.join(['?' for _ in data])})"
        self.execute_query(query, tuple(data.values()))

    def update_data(self, table_name: str, data: dict, condition: str) -> None:
        """Update one row in a table."""
        query = f"UPDATE {table_name} SET {', '.join([f'{k} = ?' for k in data.keys()])} WHERE {condition}"
        self.execute_query(query, tuple(data.values()))


# ================================
# Section for testing
# ================================
if __name__ == "__main__":

    db_manager = DatabaseManager("test.db")

    # ================================
    # Test data for the database
    # ================================

    # test_emails = [
    #     # Rainer's cactus care story - April 1
    #     {
    #         "message_id": "msg1@test.com",
    #         "date": "2025-04-01 18:23:00",
    #         "from_email": "rainer.grebin@cloud-g.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Cactus care",
    #         "body": "Hi ACP,\n\nI recently got a cactus and I'm not sure how to take care of it. Could you help me with some advice on watering and maintenance?\n\nThanks,\nRainer",
    #         "conversation_id": 1,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header1": "value1"}'
    #     },
    #     {
    #         "message_id": "msg2@test.com",
    #         "date": "2025-04-01 19:23:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "rainer.grebin@cloud-g.com",
    #         "subject": "Cactus care",
    #         "body": "Hi Rainer,\n\nCacti are relatively low-maintenance plants. They typically need to be watered once a week. I can help you stay on track by sending you weekly reminders. Would that be helpful?\n\nBest regards,\nACP",
    #         "conversation_id": 1,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header2": "value2"}'
    #     },
    #     # Rainer's cactus care story - April 2
    #     {
    #         "message_id": "msg3@test.com",
    #         "date": "2025-04-02 11:23:00",
    #         "from_email": "rainer.grebin@cloud-g.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Cactus care",
    #         "body": "Thank you for the advice! I'll try to water it once a week.\n\nRainer",
    #         "conversation_id": 1,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header3": "value3"}'
    #     },
    #     {
    #         "message_id": "msg4@test.com",
    #         "date": "2025-04-02 11:53:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "rainer.grebin@cloud-g.com",
    #         "subject": "Cactus care",
    #         "body": "Hi Rainer,\n\nWhen was the last time you watered your cactus?\n\nACP",
    #         "conversation_id": 1,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header4": "value4"}'
    #     },
    #     # Viktorija's Estonian learning story - April 2
    #     {
    #         "message_id": "msg8@test.com",
    #         "date": "2025-04-02 16:49:00",
    #         "from_email": "zezere@gmail.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Estonian language",
    #         "body": "Hi ACP,\n\nI'm having difficulties learning Estonian. The grammar is quite challenging, and I find it hard to maintain a regular practice schedule. Do you have any advice?\n\nThanks,\nViktorija",
    #         "conversation_id": 2,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header8": "value8"}'
    #     },
    #     {
    #         "message_id": "msg9@test.com",
    #         "date": "2025-04-02 17:09:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "zezere@gmail.com",
    #         "subject": "Estonian language",
    #         "body": "Hi Viktorija,\n\nRegular practice is indeed very important for language learning. Would you like assistance in setting up a consistent practice routine?\n\nBest regards,\nACP",
    #         "conversation_id": 2,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header9": "value9"}'
    #     },
    #     {
    #         "message_id": "msg10@test.com",
    #         "date": "2025-04-02 19:39:00",
    #         "from_email": "zezere@gmail.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Estonian language",
    #         "body": "Yes, daily reminders would be very helpful. I tend to forget to practice when I'm busy.\n\nViktorija",
    #         "conversation_id": 2,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header10": "value10"}'
    #     },
    #     {
    #         "message_id": "msg11@test.com",
    #         "date": "2025-04-02 20:19:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "zezere@gmail.com",
    #         "subject": "Estonian language",
    #         "body": "Sure, we can start right now. Is there a preferred time for the daily reminders?\n\nACP",
    #         "conversation_id": 2,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header11": "value11"}'
    #     },
    #     # Viktorija's Estonian learning story - April 3
    #     {
    #         "message_id": "msg12@test.com",
    #         "date": "2025-04-03 08:15:00",
    #         "from_email": "zezere@gmail.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Estonian language",
    #         "body": "Yes please, could you send reminders every day at 7 am? That would be perfect.\n\nViktorija",
    #         "conversation_id": 2,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header12": "value12"}'
    #     },
    #     {
    #         "message_id": "msg13@test.com",
    #         "date": "2025-04-03 08:30:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "zezere@gmail.com",
    #         "subject": "Estonian language",
    #         "body": "OK, we start now then. You'll receive your first reminder tomorrow at 7 am.\n\nACP",
    #         "conversation_id": 2,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header13": "value13"}'
    #     },
    #     {
    #         "message_id": "msg14@test.com",
    #         "date": "2025-04-03 10:00:00",
    #         "from_email": "zezere@gmail.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Estonian language",
    #         "body": "Thank you so much for your help!\n\nViktorija",
    #         "conversation_id": 2,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header14": "value14"}'
    #     },
    #     # Oleg's fish tank story - April 3
    #     {
    #         "message_id": "msg19@test.com",
    #         "date": "2025-04-03 11:40:00",
    #         "from_email": "olesha38@gmail.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Fish tank",
    #         "body": "Hi ACP,\n\nI need to look after my friend's fishtank that is meant for fish babies. There's a tight schedule needed to do necessary care for the fish couple that will make babies. Can you help me with reminders?\n\nThanks,\nOleg",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header19": "value19"}'
    #     },
    #     {
    #         "message_id": "msg20@test.com",
    #         "date": "2025-04-03 12:15:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "olesha38@gmail.com",
    #         "subject": "Fish tank",
    #         "body": "Hi Oleg,\n\nI can help by sending reminders exactly when it's time. What is the species of the fish? Do you need advice on care or just the schedule reminders?\n\nBest regards,\nACP",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header20": "value20"}'
    #     },
    #     {
    #         "message_id": "msg21@test.com",
    #         "date": "2025-04-03 15:15:00",
    #         "from_email": "olesha38@gmail.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Fish tank",
    #         "body": "My friend gave me the schedule and I've attached a photo of it to this email. The fish is a red tailed black shark.\n\nOleg",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header21": "value21"}'
    #     },
    #     {
    #         "message_id": "msg22@test.com",
    #         "date": "2025-04-03 16:05:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "olesha38@gmail.com",
    #         "subject": "Fish tank",
    #         "body": "I've received the attachment and read the schedule. I'll send reminders accordingly, until you tell me to stop.\n\nACP",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header22": "value22"}'
    #     },
    #     {
    #         "message_id": "msg23@test.com",
    #         "date": "2025-04-03 18:05:00",
    #         "from_email": "olesha38@gmail.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Fish tank",
    #         "body": "How do I order you to stop?\n\nOleg",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header23": "value23"}'
    #     },
    #     {
    #         "message_id": "msg24@test.com",
    #         "date": "2025-04-03 18:15:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "olesha38@gmail.com",
    #         "subject": "Fish tank",
    #         "body": "Just email me and I will stop.\n\nACP",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header24": "value24"}'
    #     },
    #     {
    #         "message_id": "msg25@test.com",
    #         "date": "2025-04-03 19:15:00",
    #         "from_email": "olesha38@gmail.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Fish tank",
    #         "body": "Okay.\n\nOleg",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header25": "value25"}'
    #     },
    #     {
    #         "message_id": "msg26@test.com",
    #         "date": "2025-04-03 18:00:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "olesha38@gmail.com",
    #         "subject": "Fish tank",
    #         "body": "Reminder: Time to check the fish tank temperature and pH levels.\n\nACP",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header26": "value26"}'
    #     },
    #     # Rainer's cactus care story - April 4
    #     {
    #         "message_id": "msg5@test.com",
    #         "date": "2025-04-04 15:26:00",
    #         "from_email": "rainer.grebin@cloud-g.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Cactus care",
    #         "body": "I watered it yesterday.\n\nRainer",
    #         "conversation_id": 1,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header5": "value5"}'
    #     },
    #     {
    #         "message_id": "msg6@test.com",
    #         "date": "2025-04-04 15:51:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "rainer.grebin@cloud-g.com",
    #         "subject": "Cactus care",
    #         "body": "Great! I'll send you a reminder in six days.\n\nACP",
    #         "conversation_id": 1,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header6": "value6"}'
    #     },
    #     # Viktorija's Estonian learning story - April 4
    #     {
    #         "message_id": "msg15@test.com",
    #         "date": "2025-04-04 07:00:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "zezere@gmail.com",
    #         "subject": "Estonian language",
    #         "body": "Good morning! Time to practice your Estonian. Today's focus: basic greetings and introductions.\n\nACP",
    #         "conversation_id": 2,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header15": "value15"}'
    #     },
    #     # Oleg's fish tank story - April 4
    #     {
    #         "message_id": "msg27@test.com",
    #         "date": "2025-04-04 05:00:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "olesha38@gmail.com",
    #         "subject": "Fish tank",
    #         "body": "Reminder: Time to feed the fish couple with special breeding diet.\n\nACP",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header27": "value27"}'
    #     },
    #     {
    #         "message_id": "msg29@test.com",
    #         "date": "2025-04-04 03:00:00",
    #         "from_email": "olesha38@gmail.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Fish tank",
    #         "body": "The fish mom has spawned!\n\nOleg",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header29": "value29"}'
    #     },
    #     {
    #         "message_id": "msg30@test.com",
    #         "date": "2025-04-04 03:20:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "olesha38@gmail.com",
    #         "subject": "Fish tank",
    #         "body": "URGENT: You need to take the couple out of the fishtank immediately, or else the mum will eat the eggs!\n\nACP",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header30": "value30"}'
    #     },
    #     {
    #         "message_id": "msg31@test.com",
    #         "date": "2025-04-04 05:20:00",
    #         "from_email": "olesha38@gmail.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Fish tank",
    #         "body": "The couple is out, the eggs are safe.\n\nOleg",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header31": "value31"}'
    #     },
    #     {
    #         "message_id": "msg32@test.com",
    #         "date": "2025-04-04 05:50:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "olesha38@gmail.com",
    #         "subject": "Fish tank",
    #         "body": "Now you need to push the button to make more light for hatching faster.\n\nACP",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header32": "value32"}'
    #     },
    #     {
    #         "message_id": "msg28@test.com",
    #         "date": "2025-04-04 18:00:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "olesha38@gmail.com",
    #         "subject": "Fish tank",
    #         "body": "Reminder: Time to check the fish tank temperature and pH levels.\n\nACP",
    #         "conversation_id": 3,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header28": "value28"}'
    #     },
    #     # Viktorija's Estonian learning story - April 5-7
    #     {
    #         "message_id": "msg16@test.com",
    #         "date": "2025-04-05 07:00:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "zezere@gmail.com",
    #         "subject": "Estonian language",
    #         "body": "Good morning! Time for your daily Estonian practice. Today's focus: numbers and counting.\n\nACP",
    #         "conversation_id": 2,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header16": "value16"}'
    #     },
    #     {
    #         "message_id": "msg17@test.com",
    #         "date": "2025-04-06 07:00:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "zezere@gmail.com",
    #         "subject": "Estonian language",
    #         "body": "Good morning! Time to practice your Estonian. Today's focus: common phrases for daily activities.\n\nACP",
    #         "conversation_id": 2,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header17": "value17"}'
    #     },
    #     {
    #         "message_id": "msg18@test.com",
    #         "date": "2025-04-07 07:00:00",
    #         "from_email": "acp@acp.com",
    #         "to_email": "zezere@gmail.com",
    #         "subject": "Estonian language",
    #         "body": "Good morning! Time for your daily Estonian practice. Today's focus: vocabulary related to food and dining.\n\nACP",
    #         "conversation_id": 2,
    #         "analyzed": 1,
    #         "processed": 1,
    #         "headers": '{"header18": "value18"}'
    #     },
    #     # New email for Viktorija's vacation notice
    #     {
    #         "message_id": "msg33@test.com",
    #         "date": "2025-04-07 20:44:00",
    #         "from_email": "zezere@gmail.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Estonian language",
    #         "body": "Hi ACP,\n\nI will be on vacation for the next week, so please don't send any reminders during that time.\n\nThanks,\nViktorija",
    #         "conversation_id": 2,
    #         "analyzed": 0,
    #         "processed": 0,
    #         "headers": '{"header33": "value33"}'
    #     },
    #     # Rainer's cactus care story - April 7
    #     {
    #         "message_id": "msg7@test.com",
    #         "date": "2025-04-07 20:53:00",
    #         "from_email": "rainer.grebin@cloud-g.com",
    #         "to_email": "acp@acp.com",
    #         "subject": "Cactus care",
    #         "body": "I watered the cactus today, but then I remembered it only needs water once a week. What should I do?\n\nRainer",
    #         "conversation_id": 1,
    #         "analyzed": 0,
    #         "processed": 0,
    #         "headers": '{"header7": "value7"}'
    #     }
    # ]

    # test_schedules = [
    #     # Cactus care schedule
    #     {
    #         "timestamp": "2025-04-11 15:51:00",
    #         "conversation_id": 1
    #     },
    #     # Estonian language schedule
    #     {
    #         "timestamp": "2025-04-08 07:00:00",
    #         "conversation_id": 2
    #     },
    #     # Fish tank schedule
    #     {
    #         "timestamp": "2025-04-07 20:58:00",
    #         "conversation_id": 3
    #     }
    # ]

    # test_conversations = [
    #     # Cactus care conversation
    #     {
    #         "id": 1,
    #         "user_id": 1,
    #         "conversation_subject": "Cactus care",
    #         "reply_needed": False
    #     },
    #     # Estonian language conversation
    #     {
    #         "id": 2,
    #         "user_id": 2,
    #         "conversation_subject": "Estonian language",
    #         "reply_needed": False
    #     },
    #     # Fish tank conversation
    #     {
    #         "id": 3,
    #         "user_id": 3,
    #         "conversation_subject": "Fish tank",
    #         "reply_needed": False
    #     }
    # ]

    # test_users = [
    #     # Rainer
    #     {
    #         "id": 1,
    #         "email": "rainer.grebin@cloud-g.com",
    #         "name": "Rainer"
    #     },
    #     # Viktorija
    #     {
    #         "id": 2,
    #         "email": "zezere@gmail.com",
    #         "name": "Viktorija"
    #     },
    #     # Oleg
    #     {
    #         "id": 3,
    #         "email": "olesha38@gmail.com",
    #         "name": "Oleg"
    #     }
    # ]

    # for email in test_emails:
    #     db_manager.insert_data("emails", email)

    # for schedule in test_schedules:
    #     db_manager.insert_data("schedules", schedule)

    # for conversation in test_conversations:
    #     db_manager.insert_data("conversations", conversation)

    # for user in test_users:
    #     db_manager.insert_data("users", user)

    # ================================
    # How to use Row object
    # ================================

    # print("\nAs dictionary:", dict(row))  # Print as dictionary
    # print("By column name:", row['name'])  # Access by column name
    # print("By index:", row[0])  # Access by index
    # print("Column names:", row.keys())  # Print all column names
