from core.conversations_db import ConversationsDB
from bot import Bot

RESTART = False


def main():
    # Step 0: init DB, Bot, check sent emails and completed processes
    conv_db = ConversationsDB()

    if not conv_db.all_replies_sent():
        print("Not all replies sent yet, returning.")
        return

    all_processes_completed = conv_db.all_processes_completed()
    if not all_processes_completed:
        if RESTART:
            print("Not all processes completed, calling bot anyway.")
        else:
            print("Not all processes completed, returning.")
            return

    bot = Bot(conv_db)

    # Step 1: set schedules & identify running conversations
    any_errors = bot.analyze_conversations()
    if any_errors:
        print("Failed to analyze all conversations, returning.")
        return

    # Step 2: write responses
    any_errors = bot.manage_running_conversations()
    if any_errors:
        print("Failed to generate or save responses for some conversations, "
              "skipping step 3 (manage_reminders).")
        return

    # Step 3: process schedules & (step 4): write reminders
    bot.manage_reminders()


if __name__ == "__main__":
    main()
