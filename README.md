# Hackathon Discord Bot

A Discord bot that tracks hackathons from a Google Spreadsheet and sends notifications about new hackathons and upcoming deadlines.

## Features

- Monitors a Google Spreadsheet for hackathon information
- Sends notifications when new hackathons are added
- Multiple configurable deadline reminders (up to 5 different days)
- Slash commands for easy setup and interaction
- Beautiful embeds for hackathon information display
- Multi-server support with per-server configuration
- Default spreadsheet with per-server customization

## Setup

1. Create a Discord bot and get your bot token from the [Discord Developer Portal](https://discord.com/developers/applications)

   - Enable the `applications.commands` scope when generating your invite link
   - Make sure to enable the Message Content Intent in your bot settings

2. Set up Google Sheets API:

   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Create a new project
   - Enable Google Sheets API
   - Create a service account
   - Download the credentials JSON file and rename it to `credentials.json`
   - Place `credentials.json` in the root directory of the project

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your configuration:

   ```
   DISCORD_TOKEN=your_discord_bot_token_here
   SPREADSHEET_ID=your_default_spreadsheet_id_here  # Optional default spreadsheet
   DEADLINE_REMINDER_DAYS=7,3,1  # Optional default reminder days
   ```

5. Run the bot:
   ```bash
   python bot.py
   ```

## Server Setup

After adding the bot to your server, an administrator needs to run the `/setup` command with the following parameters:

- `spreadsheet_id`: The ID of your Google Spreadsheet (found in the URL) - defaults to the one in .env if not specified
- `notification_channel`: Select the channel where notifications should be sent
- `hackathon_role`: Select the role to be pinged for notifications
- `reminder_days`: (Optional) Days before deadline to send reminders, comma-separated (e.g., "7,3,1")

## Commands

- `/setup` - Configure the bot for your server (admin only)
- `/hackathons` - List all current hackathons
- `/change_spreadsheet` - Change the Google Spreadsheet ID for your server (admin only)
- `/set_reminders` - Set custom reminder days for deadlines (admin only)
- `/view_config` - View current bot configuration for your server (admin only)

## Reminder Days

- Set up to 5 different reminder days for deadlines
- Format: comma-separated numbers (e.g., "7,3,1")
- Default reminder days: 7, 3, and 1 days before deadline
- Customize per server using `/set_reminders`
- All numbers must be positive
- Will be automatically sorted in descending order

## Spreadsheet Structure

The bot expects the following columns in your Google Spreadsheet:

- Name
- Website
- Date Start
- Date End
- Deadline
- Status
- Place
- Respond By
- Notes

## Features

- Per-server configuration using slash commands
- Default spreadsheet with ability to customize per server
- Multiple configurable deadline reminders
- Automatic notifications for new hackathons
- Handles missing values in spreadsheet
- Role mentions for important notifications
- Rich embeds for better information display
