# Email Accountability Bot

A simple email-based accountability partner bot that helps users achieve their goals through regular email communication.

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Create `.env` file with your email credentials
3. Set up cron job to run `main.py` regularly

## Structure

- `main.py` - Entry point
- `email_handler.py` - Email operations
- `database.py` - SQLite database operations
- `bot.py` - Core bot logic 

## Development Setup

1. Copy `.env.example` to `.env`
2. For testing email functionality:
   - Use your own email account
   - For Gmail: Create an "App Password" (don't use your main password)
   - For other providers: Check their documentation for secure app access
   - Update SMTP/IMAP servers in `email_handler.py` for your email provider
3. Update the credentials in `.env` with your test email account details