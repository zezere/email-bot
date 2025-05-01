from core.conversations_db import check_db_status
from bot import Bot


def main():
    all_processes_completed = check_db_status()
    if not all_processes_completed:
        # TODO: discuss what to do here. Is this obsolete?
        print("not all processes completed.")

    bot = Bot()
    bot.analyze_conversations()  # step 1: set schedules & identify running conversations
    any_errors = bot.manage_running_conversations()  # step 2: write responses
    if any_errors:
        print("Failed to generate or save responses for some conversations, "
              "skipping step 3 (manage_reminders).")
        return
    bot.manage_reminders()  # step 3: process schedules & (step 4): write reminders


if __name__ == "__main__":
    main()
