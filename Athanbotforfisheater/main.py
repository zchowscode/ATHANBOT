import discord
from discord.ext import commands, tasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import requests
import pytz
import os
from flask import Flask
from threading import Thread
import asyncio

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler()

prayer_counts = {}
opted_out_users = set()

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

        new_content = f"{interaction.message.content.splitlines()[0]}\n✅ **{count}** people have prayed so far.\n{interaction.message.content.splitlines()[-1]}"
        await interaction.response.edit_message(content=new_content, view=self)

class OptOutButton(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="🚫 Opt Out of 5-min Reminder", style=discord.ButtonStyle.danger)
    async def opt_out(self, interaction: discord.Interaction, button: discord.ui.Button):
        opted_out_users.add(self.user_id)
        await interaction.response.send_message("You have opted out of the 5-minute prayer reminder.", ephemeral=True)

    @discord.ui.button(label="✅ Opt In to 5-min Reminder", style=discord.ButtonStyle.success)
    async def opt_in(self, interaction: discord.Interaction, button: discord.ui.Button):
        opted_out_users.discard(self.user_id)
        await interaction.response.send_message("You have opted in to the 5-minute prayer reminder.", ephemeral=True)

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

        reminder_time = run_time - timedelta(minutes=5)
        if reminder_time > now:
            scheduler.add_job(send_5_min_reminder, 'date', run_date=reminder_time, args=[channel, prayer_name])

    scheduler.start()

async def send_5_min_reminder(channel, prayer_name):
    for member in channel.guild.members:
        if member.bot:
            continue
        if member.id not in opted_out_users:
            try:
                await member.send(f"⏳ Only **5 minutes** left until **{prayer_name}** prayer. Please prepare to pray.")
            except:
                continue

async def send_prayer_ping(channel, role, prayer_name):
    await send_dynamic_prayer_message(channel, role, prayer_name, is_test=False)

async def send_dynamic_prayer_message(channel, role, prayer_name, is_test):
    city, country = "Atlanta", "USA"
    timings = get_prayer_times(city, country)
    tz = pytz.timezone("America/New_York")
    now = datetime.now(tz)

    prayers = ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']
    next_prayer = None
    next_time = None

    for prayer in prayers:
        time_str = timings[prayer]
        hour, minute = map(int, time_str.split(":"))
        prayer_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if prayer_time <= now:
            prayer_time += timedelta(days=1)
        if next_time is None or prayer_time < next_time:
            next_time = prayer_time
            next_prayer = prayer

    diff = next_time - now
    hours, remainder = divmod(int(diff.total_seconds()), 3600)
    minutes = remainder // 60

    title = "This is a **test prayer** message!" if is_test else f"It's time for **{prayer_name}** prayer!"
    content = (
        f"{role.mention} 🕌 {title}\n"
        f"✅ **0** people have prayed so far.\n"
        f"⏳ Next prayer {next_prayer} in {hours}h {minutes}m."
    )
    view = PrayerButton(prayer_name)
    message = await channel.send(content, view=view)
    await channel.send(view=OptOutButton(message.author.id))

    key = (message.id, prayer_name)
    prayer_counts[key] = set()

    async def update_countdown():
        while True:
            await asyncio.sleep(300)
            now = datetime.now(tz)
            diff = next_time - now
            if diff.total_seconds() <= 0:
                break
            hours, remainder = divmod(int(diff.total_seconds()), 3600)
            minutes = remainder // 60
            count = len(prayer_counts[key])
            new_content = (
                f"{role.mention} 🕌 {title}\n"
                f"✅ **{count}** people have prayed so far.\n"
                f"⏳ Next prayer {next_prayer} in {hours}h {minutes}m."
            )
            await message.edit(content=new_content, view=view)

    bot.loop.create_task(update_countdown())

@bot.command()
async def testprayer(ctx):
    role = ctx.guild.get_role(1243994548624031856)
    await send_dynamic_prayer_message(ctx.channel, role, "Test", is_test=True)

@bot.command()
async def ping(ctx):
    await ctx.send("Bot is online!")

@bot.command(name='nextnamaz')
async def next_namaz(ctx):
    city = "Atlanta"
    country = "USA"
    timings = get_prayer_times(city, country)

    tz = pytz.timezone("America/New_York")
    now = datetime.now(tz)

    prayers = ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']
    next_prayer = None
    next_time = None

    for prayer in prayers:
        time_str = timings[prayer]
        hour, minute = map(int, time_str.split(":"))
        prayer_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if prayer_time < now:
            prayer_time += timedelta(days=1)
        if next_time is None or prayer_time < next_time:
            next_time = prayer_time
            next_prayer = prayer

    time_str = next_time.strftime("%I:%M %p")
    await ctx.send(f"Next prayer is **{next_prayer}** at {time_str} (Atlanta time).")

@bot.command(name='todayprayers')
async def today_prayers(ctx):
    city = "Atlanta"
    country = "USA"
    timings = get_prayer_times(city, country)

    msg = "**Today's Prayer Times (Atlanta):**\n"
    for prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
        msg += f"{prayer}: {timings[prayer]}\n"

    await ctx.send(msg)

@bot.command()
async def cmds(ctx):
    commands_list = """
**Available Commands:**
- `!ping` — Check if the bot is online.
- `!nextnamaz` — Show the next prayer time.
- `!todayprayers` — Show today's full prayer times.
- `!testprayer` — Send a test prayer message with interactive button.
- `!cmds` — Show this command list.
"""
    await ctx.send(commands_list)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    guild = bot.guilds[0]
    channel = guild.get_channel(1397290675090751508)
    role = guild.get_role(1243994548624031856)
    schedule_prayers(channel, role)

app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

bot.run(os.environ['DISCORD_TOKEN'])
