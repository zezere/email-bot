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

    def _to_dict(self, result: Union[sqlite3.Row, List[sqlite3.Row], None]) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        if result is None:
            return None
        if isinstance(result, list):
            return [dict(zip(row.keys(), row)) for row in result]
        return dict(zip(result.keys(), result))

    def _get_conversation(self, conversation_id: int) -> Optional[dict]:
        query = "SELECT * FROM conversations WHERE id = ?"
        result = self.db.execute_query(query, (conversation_id,))
        return result[0] if result else None

    def _get_conversation_emails(self, conversation_id: int) -> List[dict]:
        query = "SELECT * FROM emails WHERE conversation_id = ? ORDER BY date"
        return self.db.execute_query(query, (conversation_id,))

    def _start_tracking(self, conversation_ids: List[int], source: str) -> None:
        """Start tracking processes for given conversations if they don't have active processes.
        
        Args:
            conversation_ids: List of conversation IDs to track
            source: Source identifier for the process (e.g., 'analysis', 'processing')
        """
        # First check which conversations don't already have active processes
        active_processes_query = """
            SELECT conversation_id 
            FROM ps_list 
            WHERE conversation_id IN ({})
            AND status != 'completed'
            AND completed_at IS NULL
        """.format(','.join('?' * len(conversation_ids)))
        
        active_processes = self.db.execute_query(
            active_processes_query, 
            tuple(conversation_ids)
        )
        active_conv_ids = {row['conversation_id'] for row in active_processes}
        
        # Only create processes for conversations that don't have active ones
        new_conv_ids = [conv_id for conv_id in conversation_ids if conv_id not in active_conv_ids]
        
        if not new_conv_ids:
            return
            
        # Insert new processes using insert_data
        for conv_id in new_conv_ids:
            data = {
                'conversation_id': conv_id,
                'status': 'not_started',
                'source': source,
                'started_at': datetime.now().isoformat()
            }
            self.db.insert_data('ps_list', data)

    def _update_conversation_process_status(self, conversation_id: int, status: str) -> None:
        # Check if conversation process exists and if it is the only process that is not completed
        query = """
            SELECT * FROM ps_list 
            WHERE conversation_id = ? 
            AND status != 'completed'
            AND completed_at IS NULL
        """
        result = self.db.execute_query(query, (conversation_id,))
        if len(result) == 1:
            self.db.update_data('ps_list', {'status': status}, f"conversation_id = {conversation_id}")
            if status == "completed":
                self.db.update_data('ps_list', {'completed_at': datetime.now().isoformat()}, f"conversation_id = {conversation_id}")
            return True
        elif len(result) > 1:
            print(f"Conversation {conversation_id} has more than one incomplete process.")
            for row in result:
                print(f"  Process ID: {row['id']}, Status: {row['status']}, Source: {row['source']}, Started at: {row['started_at']}")
            return False
        else:
            print(f"Conversation {conversation_id} has no ongoing process")
            return False

    def _update_schedule(self, conversation_id: int, timestamp: datetime) -> None:
        # Check if schedule exists and if it is the only schedule
        query = """
            SELECT * FROM schedules 
            WHERE conversation_id = ? 
        """
        result = self.db.execute_query(query, (conversation_id,))
        if len(result) == 1:
            self.db.update_data('schedules', {'timestamp': timestamp}, f"conversation_id = {conversation_id}")
        elif len(result) == 0:
            self.db.insert_data('schedules', {'conversation_id': conversation_id, 'timestamp': timestamp})
            return True
        else:
            print(f"Conversation {conversation_id} has more than one schedule.")
            for row in result:
                print(f"  Schedule ID: {row['id']}, Timestamp: {row['timestamp']}")
            return False

    def _update_conversation_reply_needed_flag(self, conversation_id: int, reply_needed: bool) -> None:
        # Check if conversation exists and if it is the only conversation
        query = """
            SELECT * FROM conversations 
            WHERE id = ? 
        """
        result = self.db.execute_query(query, (conversation_id,))
        if len(result) == 1:
            self.db.update_data('conversations', {'reply_needed': reply_needed}, f"id = {conversation_id}")
            return True
        elif len(result) > 1:
            print(f"Conversation {conversation_id} has more than one conversation.")
            for row in result:
                print(f"  Conversation ID: {row['id']}, Subject: {row['conversation_subject']}")
            return False
        else:
            print(f"Conversation {conversation_id} is not in the database.")
            return False

    def _update_emails_analyzed_flags(self, conversation_id: int, analyzed: bool = True) -> None:
        # Check any unanalyzed emails exist
        query = """
            SELECT * FROM emails 
            WHERE conversation_id = ? AND analyzed = 0
        """
        result = self.db.execute_query(query, (conversation_id,))
        if len(result) > 0:
            self.db.update_data('emails', {'analyzed': analyzed}, f"conversation_id = {conversation_id}")
            return True
        else:
            print(f"Conversation {conversation_id} has no unanalyzed emails.")
            return False

    def _update_emails_processed_flags(self, conversation_id: int, processed: bool = True) -> None:
        # Check any unprocessed emails exist
        query = """
            SELECT * FROM emails 
            WHERE conversation_id = ? AND processed = 0
        """
        result = self.db.execute_query(query, (conversation_id,))
        if len(result) > 0:
            self.db.update_data('emails', {'processed': processed}, f"conversation_id = {conversation_id}")
            return True
        else:
            print(f"Conversation {conversation_id} has no unprocessed emails.")
            return False

    def get_all_conversations(self) -> List[Dict[str, Any]]:
        query = """
        SELECT
            c.id AS conversation_id,
            c.conversation_subject,
            e.id AS email_id,
            e.date,
            u.name AS user_name,
            e.from_email,
            e.to_email,
            e.subject,
            e.body,
            e.analyzed,
            e.processed
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
            conv_id = item['conversation_id']
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
                'conversation_id': conv_id,
                'user_name': group_list[0]['user_name'],
                'conversation_subject': group_list[0]['conversation_subject'],
                'emails': []
            }
            
            # Add emails to the conversation
            for row in group_list:
                if row['email_id']:  # Only add if email exists
                    email = {
                        'id': row['email_id'],
                        'date': row['date'],
                        'from_email': row['from_email'],
                        'to_email': row['to_email'],
                        'subject': row['subject'],
                        'body': row['body'],
                        'analyzed': row['analyzed'],
                        'processed': row['processed']
                    }
                    conversation['emails'].append(email)
            
            conversations.append(conversation)
        
        return conversations

    def get_unanalyzed_conversations(self, track: bool = True) -> List[Dict[str, Any]]:
        query = """
        SELECT
            c.id AS conversation_id,
            c.conversation_subject,
            e.id AS email_id,
            e.date,
            u.name AS user_name,
            e.from_email,
            e.to_email,
            e.subject,
            e.body,
            e.analyzed,
            e.processed
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
        
        # Create groups using a regular dictionary
        groups = {}
        for item in results:
            conv_id = item['conversation_id']
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
                'conversation_id': conv_id,
                'user_name': group_list[0]['user_name'],
                'conversation_subject': group_list[0]['conversation_subject'],
                'emails': []
            }
            
            # Add emails to the conversation
            for row in group_list:
                if row['email_id']:  # Only add if email exists
                    email = {
                        'id': row['email_id'],
                        'date': row['date'],
                        'from_email': row['from_email'],
                        'to_email': row['to_email'],
                        'subject': row['subject'],
                        'body': row['body'],
                        'analyzed': row['analyzed'],
                        'processed': row['processed']
                    }
                    conversation['emails'].append(email)
            
            conversations.append(conversation)
        
        # Start tracking if requested
        if track:
            conversation_ids = [conv['conversation_id'] for conv in conversations]
            self._start_tracking(conversation_ids, source="step1")
        
        return conversations

    def get_conversations_needing_reply(self) -> List[Dict[str, Any]]:
        query = """
            SELECT
            c.id AS conversation_id,
            c.conversation_subject,
            e.id AS email_id,
            e.date,
            u.name AS user_name,
            e.from_email,
            e.to_email,
            e.subject,
            e.body,
            e.analyzed,
            e.processed
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
            conv_id = item['conversation_id']
            if conv_id not in groups:
                groups[conv_id] = []
            groups[conv_id].append(item)
        
        conversations = []
        for conv_id, group_list in groups.items():
            if not group_list:
                continue
            
            # Create conversation object with common fields
            conversation = {
                'conversation_id': conv_id,
                'user_name': group_list[0]['user_name'],
                'conversation_subject': group_list[0]['conversation_subject'],
                'emails': []
            }
            
            # Add emails to the conversation
            for row in group_list:
                if row['email_id']:  # Only add if email exists
                    email = {
                        'id': row['email_id'],
                        'date': row['date'],
                        'from_email': row['from_email'],
                        'to_email': row['to_email'],
                        'subject': row['subject'],
                        'body': row['body'],
                        'analyzed': row['analyzed'],
                        'processed': row['processed']
                    }
                    conversation['emails'].append(email)
            
            conversations.append(conversation)
        
        return conversations

    def get_scheduled_conversations(self) -> List[Dict[str, Any]]:
        query = """
        SELECT
            c.id AS conversation_id,
            c.conversation_subject,
            e.id AS email_id,
            e.date,
            u.name AS user_name,
            e.from_email,
            e.to_email,
            e.subject,
            e.body,
            e.analyzed,
            e.processed
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
            conv_id = item['conversation_id']
            if conv_id not in groups:
                groups[conv_id] = []
            groups[conv_id].append(item)
        
        conversations = []
        for conv_id, group_list in groups.items():
            if not group_list:
                continue
            
            # Create conversation object with common fields
            conversation = {
                'conversation_id': conv_id,
                'user_name': group_list[0]['user_name'],
                'conversation_subject': group_list[0]['conversation_subject'],
                'emails': []
            }
            
            # Add emails to the conversation
            for row in group_list:
                if row['email_id']:  # Only add if email exists
                    email = {
                        'id': row['email_id'],
                        'date': row['date'],
                        'from_email': row['from_email'],
                        'to_email': row['to_email'],
                        'subject': row['subject'],
                        'body': row['body'],
                        'analyzed': row['analyzed'],
                        'processed': row['processed']
                    }
                    conversation['emails'].append(email)
            
            conversations.append(conversation)
        
        return conversations

 
if __name__ == "__main__":
    conversations_db = ConversationsDB()
    conversations = conversations_db.get_conversations_needing_reply()

    for conv in conversations:
        print(f"\nConversation {conv['conversation_id']}")
        print(f"Subject: {conv['conversation_subject']}")
        print(f"User: {conv['user_name']}")
        print("\nEmails:")
        for email in conv['emails']:
            print(f"  {email['date']} | From: {email['from_email']} To: {email['to_email']}")
            print(f"  Status: {'✓' if email['processed'] else '•'} processed, {'✓' if email['analyzed'] else '•'} analyzed")
            print()
