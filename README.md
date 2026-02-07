# Telegram Moderator Bot

## Overview
A Telegram bot for group moderation with a hierarchical user level system. The bot provides features like muting, banning, reporting, and spam detection.

## Project Structure
- `main.py` - Main bot application with command handlers
- `config.py` - Configuration settings and constants
- `database.py` - SQLite database operations
- `data/` - Directory for user data files (created automatically)

## Setup
1. Set the `BOT_TOKEN` environment variable with your Telegram bot token
2. Run `python main.py` to start the bot

## User Levels
1. Regular user
2. Donator  
3. Junior Moderator
4. Moderator
5. Junior Admin
6. Senior Admin

## Commands
- `/start` - Initialize bot and show user level
- `/mylevel` - Show your current level and stats
- `/list` - List users by level
- `/setlevel @username level` - Change user level (admin only)
- `/mute @username [seconds]` - Mute a user
- `/unmute @username` - Unmute a user
- `/ban @username [reason]` - Ban a user
- `/unban @username` - Unban a user
- `/report [reason]` - Report a message (reply to message)
- `/help` - Show help

## Database
Uses SQLite (bot_database.db) with tables for:
- users - User levels and info
- message_history - Message tracking
- sticker_history - Sticker spam tracking
- mutes - Mute records
- bans - Ban records
- reports - User reports

## Environment Variables
- `BOT_TOKEN` - Telegram Bot API token (required)
