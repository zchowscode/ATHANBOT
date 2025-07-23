import discord
from discord.ext import commands
import os
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import pytz
import asyncio
from flask import Flask
from threading import Thread

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)
scheduler = AsyncIOScheduler()

async def send_prayer_ping(channel, role, prayer_name):
    message = await channel.send(f"{role.mention} 🕌 It's time for **{prayer_name}** prayer!")
    await message.add_reaction("🕌")

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

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    guild = bot.guilds[0]
    channel = guild.get_channel(1397290675090751508)  # Replace with your channel ID
    role = guild.get_role(1243994548624031856)        # Replace with your role ID
    schedule_prayers(channel, role)

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

@bot.command(name='test')
async def test(ctx):
    await ctx.send("Test prayer ping will be sent in 5 seconds...")
    guild = ctx.guild
    role = guild.get_role(1397107910760202270)  # Replace with your role ID
    channel = ctx.channel
    scheduler.add_job(send_prayer_ping, 'date', run_date=datetime.utcnow() + timedelta(seconds=5), args=[channel, role, "Test"])

@bot.command(name='countdown')
async def countdown(ctx):
    city = "Atlanta"
    country = "USA"
    tz = pytz.timezone("America/New_York")
    prayers = ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']

    msg = await ctx.send("Starting countdown...")

    while True:
        timings = get_prayer_times(city, country)
        now = datetime.now(tz)

        next_prayer = None
        next_time = None

        for prayer in prayers:
            hour, minute = map(int, timings[prayer].split(":"))
            prayer_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if prayer_time < now:
                prayer_time += timedelta(days=1)
            if next_time is None or prayer_time < next_time:
                next_time = prayer_time
                next_prayer = prayer

        diff = next_time - now
        hours, remainder = divmod(int(diff.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        countdown_text = f"Next prayer: **{next_prayer}** in {hours}h {minutes}m {seconds}s."

        await msg.edit(content=countdown_text)

        if diff.total_seconds() <= 0:
            await msg.edit(content=f"It's time for **{next_prayer}** prayer! 🕌")
            break

        await asyncio.sleep(60)  # Update every minute to avoid rate limits

app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

bot.run(os.environ['DISCORD_TOKEN'])
