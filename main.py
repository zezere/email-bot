from database import init_db
from bot import Bot


def main():
    init_db()
    bot = Bot()
    bot.process_new_emails()


if __name__ == "__main__":
    main()
