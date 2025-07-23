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

# === BUTTON VIEW CLASS (one click per user) ===
class PrayerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.count = 0
        self.clicked_users = set()

    @discord.ui.button(label="I prayed 🙏", style=discord.ButtonStyle.primary, custom_id="prayer_button")
    async def prayer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.clicked_users:
            await interaction.response.send_message("You've already clicked for this prayer.", ephemeral=True)
            return

        self.clicked_users.add(interaction.user.id)
        self.count += 1

        await interaction.response.edit_message(
            content=interaction.message.content.split("\n⏳")[0] +
            f"\n\n🙏 {self.count} people clicked 'I prayed 🙏'\n" +
            interaction.message.content.split("\n")[-1],
            view=self
        )

# === PRAYER TIME API ===
def get_prayer_times(city="Atlanta", country="USA"):
    url = f"http://api.aladhan.com/v1/timingsByCity?city={city}&country={country}&method=2"
    return requests.get(url).json()['data']['timings']

# === PRAYER PING FUNCTION WITH TIMER ===
async def send_prayer_ping(channel, role, prayer_name):
    view = PrayerView()
    tz = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    timings = get_prayer_times()

    prayers = ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']
    upcoming = []
    for p in prayers:
        hour, minute = map(int, timings[p].split(":"))
        t = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if t < now:
            t += timedelta(days=1)
        upcoming.append((p, t))

    upcoming.sort(key=lambda x: x[1])
    next_prayer = next((p for p in upcoming if p[0] != prayer_name), None)

    def format_remaining(t):
        diff = t - datetime.now(tz)
        hours, rem = divmod(int(diff.total_seconds()), 3600)
        minutes, _ = divmod(rem, 60)
        return f"{hours}h {minutes}m"

    content = (
        f"{role.mention} 🕌 **Prayer Time Alert**\n"
        f"**{prayer_name}** prayer has begun!\n\n"
        f"🙏 Click the button if you've prayed.\n"
    )

    if next_prayer:
        time_left = format_remaining(next_prayer[1])
        content += f"\n⏳ Time until **{next_prayer[0]}**: {time_left}"

    msg = await channel.send(content, view=view)

    async def updater():
        while True:
            if next_prayer:
                time_left = format_remaining(next_prayer[1])
                new_content = (
                    f"{role.mention} 🕌 **Prayer Time Alert**\n"
                    f"**{prayer_name}** prayer has begun!\n\n"
                    f"🙏 Click the button if you've prayed.\n"
                    f"\n⏳ Time until **{next_prayer[0]}**: {time_left}"
                )
                try:
                    await msg.edit(content=new_content, view=view)
                except discord.NotFound:
                    break
                await asyncio.sleep(300)
            else:
                break

    bot.loop.create_task(updater())

# === SCHEDULER SETUP ===
def schedule_prayers(channel, role):
    scheduler.remove_all_jobs()
    tz = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    timings = get_prayer_times()

    for prayer_name in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
        hour, minute = map(int, timings[prayer_name].split(":"))
        run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if run_time < now:
            run_time += timedelta(days=1)
        scheduler.add_job(send_prayer_ping, 'date', run_date=run_time, args=[channel, role, prayer_name])
    scheduler.start()

# === BOT EVENTS ===
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    guild = bot.guilds[0]
    channel = guild.get_channel(1397290675090751508)
    role = guild.get_role(1243994548624031856)
    schedule_prayers(channel, role)

# === COMMANDS ===
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
        hour, minute = map(int, timings[prayer].split(":"))
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
    timings = get_prayer_times("Atlanta", "USA")
    msg = "**Today's Prayer Times (Atlanta):**\n"
    for prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
        msg += f"{prayer}: {timings[prayer]}\n"
    await ctx.send(msg)

@bot.command(name='testprayer')
async def testprayer(ctx):
    role = ctx.guild.get_role(1243994548624031856)
    await send_prayer_ping(ctx.channel, role, "Test Prayer")

# === KEEP ALIVE ===
app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

bot.run(os.environ['DISCORD_TOKEN'])
