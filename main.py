from core.conversations_db import ConversationsDB
from bot import Bot

RESTART = False


def main():
    conv_db = ConversationsDB()

    if not conv_db.all_replies_sent():
        print("Not all replies sent yet, returning.")
        return

    all_processes_completed = conv_db.check_db_status()
    if not all_processes_completed:
        if RESTART:
            print("Not all processes completed, calling bot anyway.")
        else:
            print("Not all processes completed, returning.")
            return

    bot = Bot(conv_db)
    bot.analyze_conversations()  # step 1: set schedules & identify running conversations
    any_errors = bot.manage_running_conversations()  # step 2: write responses
    if any_errors:
        print("Failed to generate or save responses for some conversations, "
              "skipping step 3 (manage_reminders).")
        return
    bot.manage_reminders()  # step 3: process schedules & (step 4): write reminders


if __name__ == "__main__":
    main()
