import discord
from discord.ext import commands, tasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import requests
import pytz
import os
from flask import Flask
from threading import Thread
import random

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler()

prayer_counts = {}  # (message_id, prayer_name): set of user_ids

class PrayerButton(discord.ui.View):
    def __init__(self, prayer_name):
        super().__init__(timeout=None)
        self.prayer_name = prayer_name

    @discord.ui.button(label="✅ I Prayed", style=discord.ButtonStyle.success, custom_id="prayed_button")
    async def prayed(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = (interaction.message.id, self.prayer_name)

        if key not in prayer_counts:
            prayer_counts[key] = set()

        if interaction.user.id in prayer_counts[key]:
            await interaction.response.send_message("You've already marked this prayer.", ephemeral=True)
            return

        prayer_counts[key].add(interaction.user.id)
        count = len(prayer_counts[key])

        # Replace entire message content (not append)
        new_content = f"🕌 It's time for **{self.prayer_name}** prayer!\n✅ **{count}** people have prayed so far."
        await interaction.response.edit_message(content=new_content, view=self)

def get_prayer_times(city="Atlanta", country="USA"):
    url = f"http://api.aladhan.com/v1/timingsByCity?city={city}&country={country}&method=2"
    return requests.get(url).json()['data']['timings']

def schedule_prayers(channel, role):
    scheduler.remove_all_jobs()
    tz = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    timings = get_prayer_times()

    for prayer_name in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
        time_str = timings[prayer_name]
        hour, minute = map(int, time_str.split(":"))
        run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if run_time < now:
            run_time += timedelta(days=1)
        scheduler.add_job(send_prayer_ping, 'date', run_date=run_time, args=[channel, role, prayer_name])
    scheduler.start()

async def send_prayer_ping(channel, role, prayer_name):
    content = f"🕌 It's time for **{prayer_name}** prayer!\n✅ **0** people have prayed so far."
    view = PrayerButton(prayer_name)
    message = await channel.send(content, view=view)

@tasks.loop(hours=5)
async def send_quran_quote():
    channel = bot.get_channel(YOUR_CHANNEL_ID)  # Replace with your channel ID
    verses = [(1, 1), (2, 255), (3, 26), (18, 110)]
    surah, ayah = random.choice(verses)
    url = f"http://api.aladhan.com/v1/quran/verse/{surah}/{ayah}"
    response = requests.get(url).json()

    arabic = response['data']['text']
    translation = response['data']['edition']['translation']

    message = f"📖 **Daily Quran Quote**\n\n{arabic}\n\n*{translation}*"
    await channel.send(message)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    guild = bot.guilds[0]
    channel = guild.get_channel(YOUR_CHANNEL_ID)  # Replace with actual channel ID
    role = guild.get_role(YOUR_ROLE_ID)  # Replace with actual role ID
    schedule_prayers(channel, role)
    send_quran_quote.start()

app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

bot.run(os.environ['DISCORD_TOKEN'])
