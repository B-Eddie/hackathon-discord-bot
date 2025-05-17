import os
import json
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import pytz
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv
from typing import List
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('hackathon_bot')

# Load environment variables
load_dotenv()

# Bot configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DEFAULT_SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
DEFAULT_REMINDER_DAYS = [int(x.strip()) for x in os.getenv('DEADLINE_REMINDER_DAYS', '7,3,1').split(',')]
CONFIG_FILE = 'guild_config.json'

class GuildConfig:
    def __init__(self):
        self.config = self.load_config()

    def load_config(self):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)

    def get_guild_config(self, guild_id: str):
        config = self.config.get(str(guild_id), {})
        # Use defaults if not set
        if 'spreadsheet_id' not in config and DEFAULT_SPREADSHEET_ID:
            config['spreadsheet_id'] = DEFAULT_SPREADSHEET_ID
        if 'reminder_days' not in config:
            config['reminder_days'] = DEFAULT_REMINDER_DAYS
        return config

    def set_guild_config(self, guild_id: str, config_data: dict):
        self.config[str(guild_id)] = config_data
        self.save_config()

class HackathonBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.guild_config = GuildConfig()
        self.tracker = None

    async def setup_hook(self):
        await self.tree.sync()

class HackathonTracker:
    def __init__(self, spreadsheet_id):
        self.service = None
        self.spreadsheet_id = spreadsheet_id
        self.setup_google_sheets()

    def setup_google_sheets(self):
        """Set up Google Sheets API connection"""
        try:
            creds = service_account.Credentials.from_service_account_file(
                'credentials.json',
                scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
            )
            self.service = build('sheets', 'v4', credentials=creds)
        except Exception as e:
            print(f"Error setting up Google Sheets: {e}")

    def get_hackathons(self):
        """Fetch hackathon data from Google Sheets"""
        try:
            sheet = self.service.spreadsheets()
            result = sheet.values().get(
                spreadsheetId=self.spreadsheet_id,
                range='A2:I'  # Assuming data starts from row 2
            ).execute()
            return result.get('values', [])
        except Exception as e:
            print(f"Error fetching hackathon data: {e}")
            return []

    def parse_date(self, date_str):
        """Parse date string to datetime object"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, '%m/%d/%Y')
        except:
            return None

bot = HackathonBot()
previous_hackathons = {}  # Dict to store previous hackathons per guild

def create_hackathon_embed(hackathon_data, title):
    """Create a Discord embed for hackathon information"""
    embed = discord.Embed(title=title, color=0x00ff00)
    
    def format_date(date_str):
        """Convert date from M/D/YYYY to Month D, YYYY"""
        if not date_str:
            return "N/A"
        try:
            date_obj = datetime.strptime(date_str, '%m/%d/%Y')
            return date_obj.strftime('%B %d, %Y')
        except:
            return date_str

    fields = {
        0: ("Name", True),
        1: ("Website", True),
        2: ("Start Date", True),
        3: ("End Date", True),
        4: ("Deadline", True),
        5: ("Status", True),
        6: ("Place", True),
        7: ("Respond By", True),
        8: ("Notes", False)
    }

    for i, (field_name, inline) in fields.items():
        if i < len(hackathon_data) and hackathon_data[i]:
            value = hackathon_data[i]
            # Format dates for specific fields
            if field_name in ["Start Date", "End Date", "Deadline", "Respond By"]:
                value = format_date(value)
            embed.add_field(name=field_name, value=value or "N/A", inline=inline)

    embed.timestamp = datetime.now()
    return embed

@tasks.loop(minutes=1)  # Changed to 1 minute for testing, can change back to 30 later
async def check_hackathons():
    """Regular check for hackathon updates and deadlines"""
    global previous_hackathons
    logger.info("Running hackathon check...")
    
    for guild_id, guild_data in bot.guild_config.config.items():
        try:
            if not all(key in guild_data for key in ['spreadsheet_id', 'notification_channel_id', 'hackathon_role_id']):
                logger.warning(f"Guild {guild_id} missing required configuration")
                continue

            channel = bot.get_channel(int(guild_data['notification_channel_id']))
            if not channel:
                logger.warning(f"Could not find channel for guild {guild_id}")
                continue

            if guild_id not in previous_hackathons:
                previous_hackathons[guild_id] = set()
                logger.info(f"Initialized tracking for guild {guild_id}")

            tracker = HackathonTracker(guild_data['spreadsheet_id'])
            hackathons = tracker.get_hackathons()
            current_hackathons = set()
            
            logger.info(f"Found {len(hackathons)} hackathons for guild {guild_id}")
            
            for hackathon in hackathons:
                if not hackathon or len(hackathon) < 1:
                    continue

                name = hackathon[0]
                current_hackathons.add(name)
                
                # Check for new hackathons
                if name not in previous_hackathons[guild_id]:
                    logger.info(f"New hackathon found in guild {guild_id}: {name}")
                    embed = create_hackathon_embed(hackathon, "New Hackathon Alert! 🎉")
                    await channel.send(
                        f"<@&{guild_data['hackathon_role_id']}> A new hackathon has been added!",
                        embed=embed
                    )

                # Check deadlines
                if len(hackathon) >= 5 and hackathon[4]:
                    deadline = tracker.parse_date(hackathon[4])
                    if deadline:
                        days_until = (deadline - datetime.now()).days
                        reminder_days = guild_data.get('reminder_days', DEFAULT_REMINDER_DAYS)
                        if days_until in reminder_days:
                            logger.info(f"Sending deadline reminder for {name} ({days_until} days)")
                            embed = create_hackathon_embed(hackathon, f"⚠️ Deadline in {days_until} days!")
                            await channel.send(
                                f"<@&{guild_data['hackathon_role_id']}> Deadline reminder!",
                                embed=embed
                            )

            # Update tracking set
            logger.info(f"Updating tracking for guild {guild_id}. Previous: {len(previous_hackathons[guild_id])}, Current: {len(current_hackathons)}")
            previous_hackathons[guild_id] = current_hackathons

        except Exception as e:
            logger.error(f"Error processing guild {guild_id}: {str(e)}", exc_info=True)

@check_hackathons.before_loop
async def before_check_hackathons():
    await bot.wait_until_ready()
    logger.info("Starting hackathon check loop...")

@bot.tree.command(name="setup", description="Configure the hackathon bot for your server")
@app_commands.describe(
    spreadsheet_id="The ID of your Google Spreadsheet",
    notification_channel="The channel where notifications should be sent",
    hackathon_role="The role to ping for hackathon notifications",
    reminder_days="Days before deadline to send reminders (up to 5 numbers, comma-separated, e.g. '7,3,1')"
)
async def setup(
    interaction: discord.Interaction,
    spreadsheet_id: str,
    notification_channel: discord.TextChannel,
    hackathon_role: discord.Role,
    reminder_days: str = None
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        return

    # Parse reminder days
    if reminder_days:
        try:
            reminder_days_list = [int(x.strip()) for x in reminder_days.split(',')]
            if not all(isinstance(x, int) and x > 0 for x in reminder_days_list):
                await interaction.response.send_message("All reminder days must be positive numbers!", ephemeral=True)
                return
            if len(reminder_days_list) > 5:
                await interaction.response.send_message("You can only set up to 5 reminder days!", ephemeral=True)
                return
            reminder_days_list.sort(reverse=True)  # Sort in descending order
        except ValueError:
            await interaction.response.send_message("Invalid reminder days format! Use comma-separated numbers (e.g., '7,3,1')", ephemeral=True)
            return
    else:
        reminder_days_list = DEFAULT_REMINDER_DAYS

    # Test Google Sheets connection
    tracker = HackathonTracker(spreadsheet_id)
    test_data = tracker.get_hackathons()
    if not tracker.service:
        await interaction.response.send_message("Failed to connect to Google Sheets. Please check your credentials and spreadsheet ID. (try adding this email as an editor of the sheet: murder-of-codes@hackathons-434015.iam.gserviceaccount.com)", ephemeral=True)
        return

    # Save configuration
    config_data = {
        'spreadsheet_id': spreadsheet_id,
        'notification_channel_id': str(notification_channel.id),
        'hackathon_role_id': str(hackathon_role.id),
        'reminder_days': reminder_days_list
    }
    
    bot.guild_config.set_guild_config(str(interaction.guild_id), config_data)
    
    await interaction.response.send_message(
        f"Configuration complete!\n"
        f"• Notifications will be sent to {notification_channel.mention}\n"
        f"• {hackathon_role.mention} will be pinged for updates\n"
        f"• Reminders will be sent {', '.join(str(x) for x in reminder_days_list)} days before deadlines",
        ephemeral=True
    )

@bot.tree.command(name="set_reminders", description="Set custom reminder days for hackathon deadlines")
@app_commands.describe(
    reminder_days="Days before deadline to send reminders (up to 5 numbers, comma-separated, e.g. '7,3,1')"
)
async def set_reminders(
    interaction: discord.Interaction,
    reminder_days: str
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        return

    try:
        reminder_days_list = [int(x.strip()) for x in reminder_days.split(',')]
        if not all(isinstance(x, int) and x > 0 for x in reminder_days_list):
            await interaction.response.send_message("All reminder days must be positive numbers!", ephemeral=True)
            return
        if len(reminder_days_list) > 5:
            await interaction.response.send_message("You can only set up to 5 reminder days!", ephemeral=True)
            return
        reminder_days_list.sort(reverse=True)  # Sort in descending order
    except ValueError:
        await interaction.response.send_message("Invalid reminder days format! Use comma-separated numbers (e.g., '7,3,1')", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    guild_config = bot.guild_config.get_guild_config(guild_id)
    guild_config['reminder_days'] = reminder_days_list
    bot.guild_config.set_guild_config(guild_id, guild_config)

    await interaction.response.send_message(
        f"Reminder days updated!\n"
        f"The bot will now send reminders {', '.join(str(x) for x in reminder_days_list)} days before deadlines.",
        ephemeral=True
    )

@bot.tree.command(name="hackathons", description="List all current hackathons")
async def list_hackathons(interaction: discord.Interaction):
    guild_config = bot.guild_config.get_guild_config(str(interaction.guild_id))
    
    if not guild_config:
        await interaction.response.send_message(
            "Bot hasn't been configured for this server yet! An administrator needs to run `/setup` first.",
            ephemeral=True
        )
        return

    tracker = HackathonTracker(guild_config['spreadsheet_id'])
    hackathons = tracker.get_hackathons()
    
    if not hackathons:
        await interaction.response.send_message("No hackathons found!", ephemeral=True)
        return

    await interaction.response.send_message("Fetching hackathons...", ephemeral=True)
    
    for hackathon in hackathons:
        if hackathon and len(hackathon) > 0:
            embed = create_hackathon_embed(hackathon, "Hackathon Information")
            await interaction.channel.send(embed=embed)

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    if not check_hackathons.is_running():
        check_hackathons.start()
        logger.info("Hackathon check loop started")

@bot.tree.command(name="change_spreadsheet", description="Change the Google Spreadsheet ID for hackathon tracking")
@app_commands.describe(
    spreadsheet_id="The new Google Spreadsheet ID to use"
)
async def change_spreadsheet(
    interaction: discord.Interaction,
    spreadsheet_id: str
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    guild_config = bot.guild_config.get_guild_config(guild_id)

    # Test Google Sheets connection with new ID
    tracker = HackathonTracker(spreadsheet_id)
    test_data = tracker.get_hackathons()
    if not tracker.service:
        await interaction.response.send_message("Failed to connect to Google Sheets. Please check your spreadsheet ID.", ephemeral=True)
        return

    # Update configuration with new spreadsheet ID
    guild_config['spreadsheet_id'] = spreadsheet_id
    bot.guild_config.set_guild_config(guild_id, guild_config)

    await interaction.response.send_message(
        f"Successfully updated the spreadsheet ID!\n"
        f"The bot will now track hackathons from the new spreadsheet.",
        ephemeral=True
    )

@bot.tree.command(name="view_config", description="View current bot configuration for this server")
async def view_config(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        return

    guild_config = bot.guild_config.get_guild_config(str(interaction.guild_id))
    
    if not guild_config:
        await interaction.response.send_message(
            "Bot hasn't been configured for this server yet! An administrator needs to run `/setup` first.",
            ephemeral=True
        )
        return

    channel = bot.get_channel(int(guild_config['notification_channel_id']))
    role = interaction.guild.get_role(int(guild_config['hackathon_role_id']))
    
    embed = discord.Embed(title="Bot Configuration", color=0x00ff00)
    embed.add_field(name="Spreadsheet ID", value=guild_config['spreadsheet_id'], inline=False)
    embed.add_field(name="Notification Channel", value=channel.mention if channel else "Not found", inline=True)
    embed.add_field(name="Hackathon Role", value=role.mention if role else "Not found", inline=True)
    embed.add_field(
        name="Reminder Days", 
        value=', '.join(str(x) for x in guild_config.get('reminder_days', DEFAULT_REMINDER_DAYS)),
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="force_check", description="Force check for new hackathons (Admin only)")
async def force_check(interaction: discord.Interaction):
    """Force a check for new hackathons"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    
    # Show current tracking state
    current_tracked = previous_hackathons.get(guild_id, set())
    await interaction.response.send_message(
        f"Currently tracking {len(current_tracked)} hackathons.\n"
        "Forcing check now...",
        ephemeral=True
    )
    
    # Force a check
    await check_hackathons()
    
    # Show new tracking state
    new_tracked = previous_hackathons.get(guild_id, set())
    await interaction.followup.send(
        f"Check complete!\n"
        f"Now tracking {len(new_tracked)} hackathons.\n"
        f"Tracked hackathons: {', '.join(sorted(new_tracked)) if new_tracked else 'None'}",
        ephemeral=True
    )

@bot.tree.command(name="debug_tracking", description="Show current hackathon tracking state (Admin only)")
async def debug_tracking(interaction: discord.Interaction):
    """Show current hackathon tracking state"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permissions to use this command!", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    tracked_hackathons = previous_hackathons.get(guild_id, set())
    
    embed = discord.Embed(title="Hackathon Tracking Debug Info", color=0x00ff00)
    embed.add_field(
        name="Currently Tracked Hackathons", 
        value='\n'.join(sorted(tracked_hackathons)) if tracked_hackathons else "None",
        inline=False
    )
    
    # Get current hackathons from sheet
    guild_config = bot.guild_config.get_guild_config(guild_id)
    if 'spreadsheet_id' in guild_config:
        tracker = HackathonTracker(guild_config['spreadsheet_id'])
        current_hackathons = tracker.get_hackathons()
        current_names = {h[0] for h in current_hackathons if h and len(h) > 0}
        
        embed.add_field(
            name="Current Hackathons in Sheet",
            value='\n'.join(sorted(current_names)) if current_names else "None",
            inline=False
        )
        
        # Show differences
        new_hackathons = current_names - tracked_hackathons
        if new_hackathons:
            embed.add_field(
                name="New Untracked Hackathons",
                value='\n'.join(sorted(new_hackathons)),
                inline=False
            )
    
    embed.set_footer(text=f"Guild ID: {guild_id}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Run the bot
bot.run(DISCORD_TOKEN) 