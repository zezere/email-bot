# Email Accountability Bot

A simple email-based accountability partner bot that helps users achieve their goals through regular email communication.

## Features
- Processes incoming emails automatically
- Moderates content using LLM
- Stores communication history in SQLite database
- Runs on a schedule using cron
- Logs all operations for monitoring

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Create `.env` file with your email credentials
3. Set up cron job to run `main.py` regularly

## Project Structure

- `main.py` - Entry point
- `bot.py` - Core bot logic for processing emails
- `email_handler.py` - Email operations (SMTP/IMAP)
- `database.py` - SQLite database operations
- `llm_handler.py` - LLM integration for content moderation
- `data/` - Contains SQLite database

## Development Setup

1. Copy `.env.example` to `.env`
2. For testing email functionality:
   - Use your own email account
   - For Gmail: Create an "App Password" (don't use your main password)
   - For other providers: Check their documentation for secure app access
   - Update SMTP/IMAP servers in `email_handler.py` for your email provider
3. Update the credentials in `.env` with your test email account details