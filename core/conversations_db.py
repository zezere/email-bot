import os
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
import sqlite3
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.database.database_manager import DatabaseManager


class ConversationsDB:
    def __init__(self):
        self.db = DatabaseManager("test.db")
        self.bot_emails = ["acp@acp.com", "accountability.partner.ai@nldr-ou.com"]

    def _to_dict(
        self, result: Union[sqlite3.Row, List[sqlite3.Row], None]
    ) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        if result is None:
            return None
        if isinstance(result, list):
            return [dict(zip(row.keys(), row)) for row in result]
        return dict(zip(result.keys(), result))

    def _start_tracking(self, conversation_ids: List[int], source: str) -> bool:
        """Start tracking processes for given conversations if they don't have active processes.

        If there are conversations already active, it will print out data about existing processes
        on those conversations and return False.

        If there are no conversations active, it will start tracking all conversations
        by adding a new process for each conversation with status 'not_started' and source
        as the provided in the source argument, and return True.

        Args:
            conversation_ids: List of conversation IDs to track
            source: Source identifier for the process (e.g., 'analysis', 'processing')
        Returns:
            True if the processes were started successfully, False if there was an error
        """
        active_processes_query = f"""
            SELECT
                id,
                conversation_id,
                status,
                source,
                started_at,
                completed_at
            FROM ps_list 
            WHERE conversation_id IN ({",".join("?" * len(conversation_ids))})
            AND (status != 'completed' OR completed_at IS NULL)
        """

        active_processes = self.db.execute_query(
            active_processes_query, tuple(conversation_ids)
        )
        # If none of the passed conversations have active process,
        # then all good, start tracking all conversations and return True
        if not active_processes:
            for conv_id in conversation_ids:
                data = {
                    "conversation_id": conv_id,
                    "status": "not_started",
                    "source": source,
                    "started_at": datetime.now().isoformat(),
                }
                self.db.insert_data("ps_list", data)
            return True
        # If some of the passed conversations have active process,
        # then print out all existing processes and return False
        else:
            print("Some (or all) of the passed conversations have active processes:\n")
            for row in active_processes:
                print(
                    f"  Process ID:      {row['id']},\n"
                    f"  Conversation ID: {row['conversation_id']},\n"
                    f"  Status & Source: {row['status']}, {row['source']},\n"
                    f"  Start & End:     {row['started_at']}, {row['completed_at']}\n"
                )
            return False

    def _update_conversation_process_status(
        self, conversation_id: int, status: str
    ) -> None:
        """Update the status of a conversation process.
        If there is more than one incomplete process with the same conversation_id, it will print out the existing processes and return False.
        If the conversation process is not in the database, it will print out a message and return False.

        Args:
            conversation_id: The ID of the conversation to update the related process
            status: The new status for the process
        Returns:
            True if the status was updated successfully, False if there was an error
        """
        query = """
            SELECT * FROM ps_list 
            WHERE conversation_id = ? 
            AND (
                status != 'completed'
                OR completed_at IS NULL
            )
        """
        result = self.db.execute_query(query, (conversation_id,))
        if len(result) == 1:
            self.db.update_data(
                "ps_list", {"status": status}, f"conversation_id = {conversation_id}"
            )
            if status == "completed":
                self.db.update_data(
                    "ps_list",
                    {"completed_at": datetime.now().isoformat()},
                    f"conversation_id = {conversation_id}",
                )
            return True
        elif len(result) > 1:
            print(
                f"Conversation {conversation_id} has more than one incomplete process."
            )
            for row in result:
                print(
                    f"  Process ID: {row['id']}, Status: {row['status']}, Source: {row['source']}, Started at: {row['started_at']}"
                )
            return False
        else:
            print(f"Conversation {conversation_id} has no ongoing process")
            return False

    def _update_schedule(self, conversation_id: int, timestamp: datetime) -> None:
        """Update the schedule for a conversation, if it exists, or insert a new one.
        In case of more than one schedule, it will print out the existing schedules and return False.

        Args:
            conversation_id: The ID of the conversation to update
            timestamp: The new timestamp for the schedule
        Returns:
            True if the schedule was updated successfully, False if there was an error
        """
        query = """
            SELECT * FROM schedules 
            WHERE conversation_id = ? 
        """
        result = self.db.execute_query(query, (conversation_id,))
        if len(result) == 1:
            self.db.update_data(
                "schedules",
                {"timestamp": timestamp},
                f"conversation_id = {conversation_id}",
            )
            return True
        elif len(result) == 0:
            self.db.insert_data(
                "schedules",
                {"conversation_id": conversation_id, "timestamp": timestamp},
            )
            return True
        else:
            print(f"Conversation {conversation_id} has more than one schedule.")
            for row in result:
                print(f"  Schedule ID: {row['id']}, Timestamp: {row['timestamp']}")
            return False

    def _update_conversation_reply_needed_flag(
        self, conversation_id: int, reply_needed: bool
    ) -> None:
        """Update the reply needed flag for a conversation.
        If there is more than one conversation with the same id, it will print out the existing conversations and return False.
        If the conversation is not in the database, it will print out a message and return False.

        Args:
            conversation_id: The ID of the conversation to update
            reply_needed: The new reply needed flag
        Returns:
            True if the reply_needed flag was updated successfully, False if there was an error
        """
        query = """
            SELECT * FROM conversations 
            WHERE id = ? 
        """
        result = self.db.execute_query(query, (conversation_id,))
        # TODO: create a separate function to do checks and return data and True or False
        if len(result) == 1:
            self.db.update_data(
                "conversations",
                {"reply_needed": reply_needed},
                f"id = {conversation_id}",
            )
            return True
        elif len(result) > 1:
            print(f"Conversation {conversation_id} has more than one conversation.")
            for row in result:
                print(
                    f"  Conversation ID: {row['id']}, Subject: {row['conversation_subject']}"
                )
            return False
        else:
            print(f"Conversation {conversation_id} is not in the database.")
            return False

    def _save_reply(self, conversation_id: int, reply_message: str) -> None:
        """Save the reply in the prepared_replies table.
        For the email subject, it will use the conversation subject.
        If there is more than one conversation with the same id, it will print out the existing conversations and return False.
        If the conversation is not in the database, it will print out a message and return False.

        Args:
            conversation_id: The ID of the conversation to save the reply
            reply_message: The reply message to save
        Returns:
            True if the reply was saved successfully, False if there was an error
        """
        query = """
            SELECT DISTINCT conversation_subject FROM conversations 
            WHERE id = ? 
        """
        result = self.db.execute_query(query, (conversation_id,))
        # TODO: create a separate function to do checks and return data and True or False
        if len(result) == 1:
            conversation_subject = result[0]["conversation_subject"]
            data = {
                "conversation_id": conversation_id,
                "reply_subject": conversation_subject,
                "reply_message": reply_message,
                "timestamp": datetime.now().isoformat(),
            }
            self.db.insert_data("prepared_replies", data)
            return True
        elif len(result) > 1:
            print(f"Conversation {conversation_id} has more than one conversation.")
            for row in result:
                print(
                    f"  Conversation ID: {row['id']}, Subject: {row['conversation_subject']}"
                )
            return False
        else:
            print(f"Conversation {conversation_id} has no conversation subject.")
            return False

    def _update_emails_analyzed_flags(
        self, conversation_id: int, analyzed: bool = True
    ) -> None:
        # Check any unanalyzed emails exist
        query = """
            SELECT * FROM emails 
            WHERE conversation_id = ? AND analyzed = 0
        """
        result = self.db.execute_query(query, (conversation_id,))
        if len(result) > 0:
            self.db.update_data(
                "emails", {"analyzed": analyzed}, f"conversation_id = {conversation_id}"
            )
            return True
        else:
            print(f"Conversation {conversation_id} has no unanalyzed emails.")
            return False

    def _update_emails_processed_flags(
        self, conversation_id: int, processed: bool = True
    ) -> None:
        # Check any unprocessed emails exist
        query = """
            SELECT * FROM emails 
            WHERE conversation_id = ? AND processed = 0
        """
        result = self.db.execute_query(query, (conversation_id,))
        if len(result) > 0:
            self.db.update_data(
                "emails",
                {"processed": processed},
                f"conversation_id = {conversation_id}",
            )
            return True
        else:
            print(f"Conversation {conversation_id} has no unprocessed emails.")
            return False

    # Not used for Bot to work but may be useful for testing
    def get_all_conversations(self) -> List[Dict[str, Any]]:
        query = """
        SELECT
            c.id AS conversation_id,
            u.name AS user_name,
            c.conversation_subject,
            e.id AS email_id,
            e.date,
            e.from_email,
            e.to_email,
            e.body
        FROM
            conversations c
            LEFT JOIN users u ON c.user_id = u.id
            LEFT JOIN emails e ON c.id = e.conversation_id
        ORDER BY date
        """
        rows = self.db.execute_query(query)
        results = self._to_dict(rows)

        # Create groups using a regular dictionary
        groups = {}
        for item in results:
            conv_id = item["conversation_id"]
            if conv_id not in groups:
                groups[conv_id] = []
            groups[conv_id].append(item)

        # Then iterate over the groups
        conversations = []
        for conv_id, group_list in groups.items():
            if not group_list:
                continue

            # Create conversation object with common fields
            conversation = {
                "conversation_id": conv_id,
                "user_name": group_list[0]["user_name"],
                "conversation_subject": group_list[0]["conversation_subject"],
                "emails": [],
            }

            # Add emails to the conversation
            for row in group_list:
                if row["email_id"]:  # Only add if email exists
                    role = "user"
                    if row["from_email"] in self.bot_emails:
                        role = "assistant"
                    elif row["to_email"] in self.bot_emails:
                        role = "user"
                    else:
                        print(f"Email {row['email_id']} has no bot email")
                        role = "unknown"
                    email = {
                        "id": row["email_id"],
                        "date": datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S"),
                        "role": role,
                        "body": row["body"],
                    }
                    conversation["emails"].append(email)

            conversations.append(conversation)

        return conversations

    def check_db_status(self) -> bool:
        """Check if there are any incomplete processes in the database.
        If there are, it will print out the existing processes and return False.
        If there are no incomplete processes, it will return True.
        """
        query = """
            SELECT * FROM ps_list 
            WHERE status != 'completed' 
            OR completed_at IS NULL
        """
        result = self.db.execute_query(query)

        if not result:
            return True

        print("Found incomplete processes:")
        for row in result:
            print(
                f"  Process ID: {row['id']}, Conversation ID: {row['conversation_id']}, "
                f"Status: {row['status']}, Source: {row['source']}, Started at: {row['started_at']}"
            )
        return False

    def get_unanalyzed_conversations(self, track: bool) -> List[Dict[str, Any]] | bool:
        """Get all conversations that have at least one unanalyzed email.
        If track is True, then start tracking the conversations.

        Args:
            track: Whether to start tracking the conversations
        Returns:
            A list of conversations that have at least one unanalyzed email
            or False if tracking is True and at least one conversation has an active process
        """
        query = """
        SELECT
            c.id AS conversation_id,
            u.name AS user_name,
            c.conversation_subject,
            e.id AS email_id,
            e.date,
            e.from_email,
            e.to_email,
            e.body
        FROM
            conversations c
            LEFT JOIN users u ON c.user_id = u.id
            LEFT JOIN emails e ON c.id = e.conversation_id
        WHERE
            c.id IN (
                SELECT DISTINCT conversation_id
                FROM emails
                WHERE analyzed = 0 
                )
        ORDER BY date
        """
        rows = self.db.execute_query(query)
        results = self._to_dict(rows)

        groups = {}
        for item in results:
            conv_id = item["conversation_id"]
            if conv_id not in groups:
                groups[conv_id] = []
            groups[conv_id].append(item)

        conversations = []
        for conv_id, group_list in groups.items():
            if not group_list:
                continue

            # Create conversation object with common fields
            conversation = {
                "conversation_id": conv_id,
                "user_name": group_list[0]["user_name"],
                "conversation_subject": group_list[0]["conversation_subject"],
                "emails": [],
            }

            # Add emails to the conversation
            for row in group_list:
                if row["email_id"]:  # Only add if email exists
                    role = "user"
                    if row["from_email"] in self.bot_emails:
                        role = "assistant"
                    elif row["to_email"] in self.bot_emails:
                        role = "user"
                    else:
                        print(f"Email {row['email_id']} has no bot email")
                        role = "unknown"
                    email = {
                        "id": row["email_id"],
                        "date": datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S"),
                        "role": role,
                        "body": row["body"],
                    }
                    conversation["emails"].append(email)

            conversations.append(conversation)

        # Start tracking if requested
        if track:
            conversation_ids = [conv["conversation_id"] for conv in conversations]
            success = self._start_tracking(conversation_ids, source="step1")
            if not success:
                print(
                    f"ERROR in {self.get_unanalyzed_conversations.__name__}: Some (or all) conversations have active processes"
                )
                return False

        return conversations

    def get_conversations_needing_reply(self) -> List[Dict[str, Any]]:
        """Get all conversations that need a reply, based on reply_needed flag.
        Tracking is not needed here, because we're not starting any new processes.

        Returns:
            A list of conversations that need a reply
        """
        query = """
        SELECT
            c.id AS conversation_id,
            u.name AS user_name,
            c.conversation_subject,
            e.id AS email_id,
            e.date,
            e.from_email,
            e.to_email,
            e.body
        FROM
            conversations c
            LEFT JOIN users u ON c.user_id = u.id
            LEFT JOIN emails e ON c.id = e.conversation_id
        WHERE reply_needed = 1
        ORDER BY date
        """
        rows = self.db.execute_query(query)
        results = self._to_dict(rows)

        groups = {}
        for item in results:
            conv_id = item["conversation_id"]
            if conv_id not in groups:
                groups[conv_id] = []
            groups[conv_id].append(item)

        conversations = []
        for conv_id, group_list in groups.items():
            if not group_list:
                continue

            # Create conversation object with common fields
            conversation = {
                "conversation_id": conv_id,
                "user_name": group_list[0]["user_name"],
                "conversation_subject": group_list[0]["conversation_subject"],
                "emails": [],
            }

            # Add emails to the conversation
            for row in group_list:
                if row["email_id"]:  # Only add if email exists
                    role = "user"
                    if row["from_email"] in self.bot_emails:
                        role = "assistant"
                    elif row["to_email"] in self.bot_emails:
                        role = "user"
                    else:
                        print(f"Email {row['email_id']} has no bot email")
                        role = "unknown"
                    email = {
                        "id": row["email_id"],
                        "date": datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S"),
                        "role": role,
                        "body": row["body"],
                    }
                    conversation["emails"].append(email)

            conversations.append(conversation)

        return conversations

    # TODO: this function also needs to return awareness time and if a conversation
    # has been replied to in a previous loop, then return the reply as well
    def get_scheduled_conversations(self, track: bool) -> List[Dict[str, Any]]:
        query = """
        SELECT
            c.id AS conversation_id,
            u.name AS user_name,
            c.conversation_subject,
            e.id AS email_id,
            e.date,
            e.from_email,
            e.to_email,
            e.body
        FROM
            conversations c
            LEFT JOIN users u ON c.user_id = u.id
            LEFT JOIN emails e ON c.id = e.conversation_id
        WHERE
            c.id IN (
                SELECT DISTINCT conversation_id
                FROM schedules
                WHERE datetime(timestamp) < datetime('now') 
            )
        ORDER BY date
        """
        rows = self.db.execute_query(query)
        results = self._to_dict(rows)

        groups = {}
        for item in results:
            conv_id = item["conversation_id"]
            if conv_id not in groups:
                groups[conv_id] = []
            groups[conv_id].append(item)

        conversations = []
        for conv_id, group_list in groups.items():
            if not group_list:
                continue

            # Create conversation object with common fields
            conversation = {
                "conversation_id": conv_id,
                "user_name": group_list[0]["user_name"],
                "conversation_subject": group_list[0]["conversation_subject"],
                "emails": [],
            }

            # Add emails to the conversation
            for row in group_list:
                if row["email_id"]:  # Only add if email exists
                    role = "user"
                    if row["from_email"] in self.bot_emails:
                        role = "assistant"
                    elif row["to_email"] in self.bot_emails:
                        role = "user"
                    else:
                        print(f"Email {row['email_id']} has no bot email")
                        role = "unknown"
                    email = {
                        "id": row["email_id"],
                        "date": datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S"),
                        "role": role,
                        "body": row["body"],
                    }
                    conversation["emails"].append(email)

            conversations.append(conversation)

        # Start tracking if requested
        if track:
            conversation_ids = [conv["conversation_id"] for conv in conversations]
            success = self._start_tracking(conversation_ids, source="step3")
            if not success:
                print(
                    f"ERROR in {self.get_scheduled_conversations.__name__}: Some (or all) conversations have active processes"
                )
                return False

        return conversations

    def update_data_after_step1(
        self,
        conversation_id: int,
        new_schedule: datetime = None,
        new_reply_needed: bool = False,
    ) -> bool:
        """Update the data after step 1:
        1. Update schedule in schedules table (if provided)
        2. Update emails analyzed flags (for all emails in that conversation) in emails table
        3. Update reply needed flag in conversations table
        4. If reply is needed, then process is not complete yet, so we:
            - Update converastion process status to "analyzed" (meaning, waiting to be "processed")
            - Leave processed flags as is
           If reply is not needed, then we're done with this conversation and we:
            - Update conversation process status to "completed"
            - Update emails processed flags (for all emails in that conversation) in emails table

        Args:
            conversation_id: The ID of the conversation to update
            new_schedule: The new schedule for the conversation (optional)
            new_reply_needed: The new reply needed flag (False by default)
        Returns:
            True if all updates were successful, False if there was at least one error
        """

        # 1. Update schedule (if provided)
        if new_schedule:
            schedule_update_success = self._update_schedule(
                conversation_id, new_schedule
            )
        else:
            schedule_update_success = True

        # 2. Update emails ANALYZED flags
        emails_analyzed_update_success = self._update_emails_analyzed_flags(
            conversation_id, True
        )

        # 3. Update reply needed flag in conversations table
        reply_needed_update_success = self._update_conversation_reply_needed_flag(
            conversation_id, new_reply_needed
        )

        # 4. Update emails PROCESSED flags, depending whether reply is needed or not
        #    and update conversation process status, depending whether reply is needed or not
        if new_reply_needed:
            # if reply is needed, then PROCESSED flag does not need update
            # so the success flag is set to True
            conversation_process_status_update_success = (
                self._update_conversation_process_status(conversation_id, "analyzed")
            )
            emails_processed_update_success = True
        else:
            conversation_process_status_update_success = (
                self._update_conversation_process_status(conversation_id, "completed")
            )
            emails_processed_update_success = self._update_emails_processed_flags(
                conversation_id, True
            )

        all_updates_successful = (
            schedule_update_success  # 1.
            and emails_analyzed_update_success  # 2.
            and reply_needed_update_success  # 3.
            and emails_processed_update_success  # 4.
            and conversation_process_status_update_success  # 4.
        )
        if not all_updates_successful:
            print(
                f"Error in {self.update_data_after_step1.__name__} for conversation ID {conversation_id}: \n"
                f"  all_updates_successful: {all_updates_successful}, \n"
                f"  schedule_update_success: {schedule_update_success}, \n"
                f"  emails_analyzed_update_success: {emails_analyzed_update_success}, \n"
                f"  reply_needed_update_success: {reply_needed_update_success}, \n"
                f"  emails_processed_update_success: {emails_processed_update_success}, \n"
                f"  conversation_process_status_update_success: {conversation_process_status_update_success}\n"
            )
            return False
            # IMPORTANT NOTE: if one of updates failed, we need to roll back all the updates
        return True

    def update_data_after_step2(self, conversation_id: int, reply_message: str) -> None:
        """Update the data after step 2:
        1. Save the reply in the prepared_replies table
        2. Update conversation flag reply_needed to False
        3. Update emails processed flags (for all emails in that conversation) in emails table
        4. Update conversation process status to "completed"

        Args:
            conversation_id: The ID of the conversation to update
            reply: The reply to save
        Returns:
            True if all updates were successful, False if there was at least one error
        """
        reply_saved = self._save_reply(conversation_id, reply_message)

        reply_needed_updated = self._update_conversation_reply_needed_flag(
            conversation_id, False
        )
        emails_processed_updated = self._update_emails_processed_flags(
            conversation_id, True
        )
        conversation_process_status_updated = self._update_conversation_process_status(
            conversation_id, "completed"
        )

        all_updates_successful = (
            reply_saved
            and reply_needed_updated
            and emails_processed_updated
            and conversation_process_status_updated
        )
        if not all_updates_successful:
            print(f"Error updating data for conversation {conversation_id}")
            return False
            # IMPORTANT NOTE: if one of updates failed, we need to roll back all the updates
        return True

    # NOTE: needs discussion what to do with policies
    def update_data_after_step3(
        self, conversation_id: int, new_schedule: datetime
    ) -> None:
        """Update the data after step 3:
        1. Update schedule in schedules table

        Args:
            conversation_id: The ID of the conversation to update
        """
        schedule_updated = self._update_schedule(conversation_id, new_schedule)
        if not schedule_updated:
            print(f"Error updating schedule for conversation {conversation_id}")
            return False
        return True

    def update_data_after_step4(self, conversation_id: int, reply_message: str) -> None:
        """Update the data after step 4:
        1. Save the reply in the prepared_replies table
        2. Update conversation flag reply_needed to False
        3. Update emails processed flags (for all emails in that conversation) in emails table
        4. Update conversation process status to "completed"

        Args:
            conversation_id: The ID of the conversation to update
            reply_message: The reply to save
        Returns:
            True if all updates were successful, False if there was at least one error
        """
        reply_saved_success = self._save_reply(conversation_id, reply_message)
        reply_needed_update_success = self._update_conversation_reply_needed_flag(
            conversation_id, False
        )
        emails_processed_update_success = self._update_emails_processed_flags(
            conversation_id, True
        )
        conversation_process_status_update_success = (
            self._update_conversation_process_status(conversation_id, "completed")
        )

        all_updates_successful = (
            reply_saved_success
            and reply_needed_update_success
            and emails_processed_update_success
            and conversation_process_status_update_success
        )
        if not all_updates_successful:
            print(f"Error updating data for conversation {conversation_id}")
            return False


# ==================================================================
# Section for testing how database manager works - NOT FOR PRODUCTION
# ==================================================================
if __name__ == "__main__":
    cdb = ConversationsDB()
    # cdb.check_db_status()
    # conversations = cdb.get_scheduled_conversations()
    # success = cdb._start_tracking([3], "step3")
    # result = cdb.get_unanalyzed_conversations(track=True)

    # success = cdb.update_data_after_step1(4, new_schedule=None, new_reply_needed=False)
