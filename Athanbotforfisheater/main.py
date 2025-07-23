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
import asyncio

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler()

prayer_counts = {}  # (message_id, prayer_name): set of user_ids
update_tasks = {}  # message_id: asyncio.Task for updating countdown

PRAYERS = ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']
TIMEZONE = pytz.timezone("America/New_York")
CHANNEL_ID = 1397290675090751508
ROLE_ID = 1243994548624031856

class PrayerButton(discord.ui.View):
    def __init__(self, prayer_name, next_prayer, next_prayer_time):
        super().__init__(timeout=None)
        self.prayer_name = prayer_name
        self.next_prayer = next_prayer
        self.next_prayer_time = next_prayer_time

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

        countdown_str = get_time_until(self.next_prayer_time)
        new_content = (
            f"🕌 It's time for **{self.prayer_name}** prayer!\n"
            f"✅ **{count}** people have prayed so far.\n"
            f"⏳ Next prayer **{self.next_prayer}** in {countdown_str}."
        )
        await interaction.response.edit_message(content=new_content, view=self)

def get_prayer_times(city="Atlanta", country="USA"):
    url = f"http://api.aladhan.com/v1/timingsByCity?city={city}&country={country}&method=2"
    return requests.get(url).json()['data']['timings']

def get_next_prayer_and_time(timings):
    now = datetime.now(TIMEZONE)
    next_prayer = None
    next_time = None
    for prayer in PRAYERS:
        time_str = timings[prayer]
        hour, minute = map(int, time_str.split(":"))
        prayer_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if prayer_time < now:
            prayer_time += timedelta(days=1)
        if next_time is None or prayer_time < next_time:
            next_time = prayer_time
            next_prayer = prayer
    return next_prayer, next_time

def get_time_until(future_time):
    now = datetime.now(TIMEZONE)
    diff = future_time - now
    total_sec = int(diff.total_seconds())
    if total_sec < 0:
        return "0m"
    hours, remainder = divmod(total_sec, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"

async def update_prayer_message(message, prayer_name, next_prayer, next_prayer_time):
    key = (message.id, prayer_name)
    while True:
        if key not in prayer_counts:
            count = 0
        else:
            count = len(prayer_counts[key])
        countdown_str = get_time_until(next_prayer_time)
        new_content = (
            f"🕌 It's time for **{prayer_name}** prayer!\n"
            f"✅ **{count}** people have prayed so far.\n"
            f"⏳ Next prayer **{next_prayer}** in {countdown_str}."
        )
        try:
            await message.edit(content=new_content)
        except discord.NotFound:
            break
        await asyncio.sleep(300)  # Update every 5 minutes

def schedule_prayers(channel, role):
    scheduler.remove_all_jobs()
    now = datetime.now(TIMEZONE)
    timings = get_prayer_times()
    for prayer_name in PRAYERS:
        time_str = timings[prayer_name]
        hour, minute = map(int, time_str.split(":"))
        run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if run_time < now:
            run_time += timedelta(days=1)
        scheduler.add_job(send_prayer_ping, 'date', run_date=run_time, args=[channel, role, prayer_name])
    scheduler.start()

async def send_prayer_ping(channel, role, prayer_name):
    timings = get_prayer_times()
    next_prayer, next_prayer_time = get_next_prayer_and_time(timings)
    content = (
        f"🕌 It's time for **{prayer_name}** prayer!\n"
        f"✅ **0** people have prayed so far.\n"
        f"⏳ Next prayer **{next_prayer}** in {get_time_until(next_prayer_time)}."
    )
    view = PrayerButton(prayer_name, next_prayer, next_prayer_time)
    message = await channel.send(content, view=view)
    # Start background task to update countdown every 5 mins
    task = asyncio.create_task(update_prayer_message(message, prayer_name, next_prayer, next_prayer_time))
    update_tasks[message.id] = task

@bot.command()
async def testprayer(ctx):
    timings = get_prayer_times()
    next_prayer, next_prayer_time = get_next_prayer_and_time(timings)
    content = (
        f"🕌 This is a **test prayer** message!\n"
        f"✅ **0** people have prayed so far.\n"
        f"⏳ Next prayer **{next_prayer}** in {get_time_until(next_prayer_time)}."
    )
    view = PrayerButton("Test", next_prayer, next_prayer_time)
    message = await ctx.send(content, view=view)
    task = asyncio.create_task(update_prayer_message(message, "Test", next_prayer, next_prayer_time))
    update_tasks[message.id] = task

@bot.command()
async def countdown(ctx):
    timings = get_prayer_times()
    next_prayer, next_prayer_time = get_next_prayer_and_time(timings)
    time_left = get_time_until(next_prayer_time)
    await ctx.send(f"⏳ Next prayer is **{next_prayer}** in {time_left}.")

@bot.command()
async def ping(ctx):
    await ctx.send("Bot is online!")

@bot.command(name='nextnamaz')
async def next_namaz(ctx):
    city = "Atlanta"
    country = "USA"
    timings = get_prayer_times(city, country)

    now = datetime.now(TIMEZONE)

    next_prayer, next_time = get_next_prayer_and_time(timings)

    time_str = next_time.strftime("%I:%M %p")
    await ctx.send(f"Next prayer is **{next_prayer}** at {time_str} (Atlanta time).")

@bot.command(name='todayprayers')
async def today_prayers(ctx):
    city = "Atlanta"
    country = "USA"
    timings = get_prayer_times(city, country)

    msg = "**Today's Prayer Times (Atlanta):**\n"
    for prayer in PRAYERS:
        msg += f"{prayer}: {timings[prayer]}\n"

    await ctx.send(msg)

@tasks.loop(hours=5)
async def send_quran_quote():
    channel = bot.get_channel(CHANNEL_ID)
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
    channel = guild.get_channel(CHANNEL_ID)
    role = guild.get_role(ROLE_ID)
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
