import os
import json
import logging
import sqlite3
import aiohttp
import pytz
import pandas as pd
import matplotlib.pyplot as plt
import io
from contextlib import contextmanager
from datetime import datetime, timedelta, time
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes, 
    PicklePersistence
)

# ---------------- Configuration ----------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "none")
LLAMA_SERVER_URL = os.environ.get("AI_SERVER_URL", "http://ai-server:8080/completion")

# Timezone Setup
TZ_ET = pytz.timezone('US/Eastern')
NIGHT_START_HOUR = 23 
NIGHT_END_HOUR = 8

CATEGORIES = [
    "Sleep", "Work", "Hobbies", "Freelance", "Exercise", 
    "Friends", "Leisure", "Dating", "Family", "Chores", "Travel", "Misc"
]

# Default priorities to help future changes for contextualized responses
DEFAULT_PRIORITIES = {
    "Sleep": 5,
    "Work": 5,
    "Exercise": 5,
    "Hobbies": 4,
    "Freelance": 4,
    "Family": 3,
    "Friends": 3,
    "Chores": 3,
    "Leisure": 2,
    "Dating": 2,
    "Travel": 2,
    "Misc": 1
}

AI_RULES = (
    "Hobbies = skill-building or long-term interests. \n"
    "Leisure = passive or unstructured consumption. \n"
    "Do not reassure unless behavior supports it. \n"
)

os.makedirs("data", exist_ok=True)
DB_PATH = "data/shadow_tracker.db"
PERSISTENCE_PATH = "data/bot_persistence.pickle"
CHECKIN_INTERVAL_SEC = 3600  # 1 hour

# Set Matplotlib backend to Agg (no display)
plt.switch_backend('Agg')

# ---------------- Logging ----------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- Database ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            category TEXT,
            text TEXT
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS priorities (
            category TEXT PRIMARY KEY,
            weight INTEGER NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()
    
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def save_entry(category: str, text: str, timestamp=None):
    if timestamp is None:
        timestamp = datetime.now(pytz.UTC)
    else:
        timestamp = timestamp.astimezone(pytz.UTC)

    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO entries (timestamp, category, text) VALUES (?, ?, ?)",
            (timestamp.strftime('%Y-%m-%d %H:%M:%S'), category, text)
        )
    
def seed_priorities():
    with get_db() as conn:
        c = conn.cursor()
        for cat, weight in DEFAULT_PRIORITIES.items():
            c.execute(
                "INSERT OR IGNORE INTO priorities (category, weight) VALUES (?, ?)",
                (cat, weight)
            )

    
def get_priority_weight(category: str) -> int:
    with get_db() as conn:
        c = conn.cursor()
        row = c.execute(
            "SELECT weight FROM priorities WHERE category = ?",
            (category,)
        ).fetchone()
    return row[0] if row else 1

    
def get_all_priorities():
    with get_db() as conn:
        c = conn.cursor()
        rows = c.execute(
            "SELECT category, weight FROM priorities"
        ).fetchall()
    return dict(rows)


async def show_priorities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_db() as conn:
        c = conn.cursor()
        rows = c.execute(
            "SELECT category, weight FROM priorities ORDER BY weight DESC"
        ).fetchall()

    msg = "**Current Priorities**\n\n"
    for cat, w in rows:
        msg += f"{cat}: {w}\n"

    await update.message.reply_text(msg, parse_mode="Markdown")


async def set_priority(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        category = context.args[0]
        weight = int(context.args[1])
        assert category in CATEGORIES
        assert 1 <= weight <= 5
    except Exception:
        await update.message.reply_text(
            "Usage: /set_priority <Category> <1–5>"
        )
        return

    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO priorities (category, weight) VALUES (?, ?)",
            (category, weight)
        )

    await update.message.reply_text(
        f"Priority updated: {category} → {weight}"
    )


# ---------------- AI & Logic ----------------
async def analyze_with_ai(text: str):
    priorities = get_all_priorities()
    priorities_text = ", ".join(
        f"{cat}:{w}" for cat, w in sorted(
            priorities.items(), key=lambda x: -x[1]
        )
    )
    
    
    # The Prompt: Defines the "Anti-Liar" Persona
    prompt = (
        f"You are a stoic, compassionate, yet firm accountability coach.\n"
        f"The user is fighting a self-sabotaging voice called 'The Liar'.\n\n"
        f"User priorities (higher = more important): {priorities_text}\n\n"
        f"{AI_RULES}\n\n"
        f"Your task:\n"
        f"1. CLASSIFY the activity into exactly one of: {CATEGORIES}.\n"
        f"2. RESPONSE (1–2 sentences):\n"
        f"- Reinforce aligned behavior briefly.\n"
        f"- If misaligned with priorities, state the consequence plainly.\n\n"
        f"Input: \"{text}\"\n\n"
        f"Output JSON only: {{\"category\": \"...\", \"response\": \"...\"}}"
        f"End your response strictly with <END_JSON>"
    )


    async with aiohttp.ClientSession() as session:
        try:
            payload = {
                "prompt": prompt, 
                "n_predict": 100, # Increased for the text response
                "temperature": 0.3, # Slightly creative for the advice
                "stop": ["<END_JSON>"] # Stop after JSON closes
            }
            async with session.post(LLAMA_SERVER_URL, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Clean up response to ensure valid JSON
                    content = data.get("content", data.get("completion", "")).strip()
                    content = content.split("<END_JSON>")[0].strip()
                    content = content[content.find("{"):] if "{" in content else content


                    try:
                        result = json.loads(content)
                        # Validate category
                        cat = result.get("category", "Misc")
                        found_cat = "Misc"
                        for c in CATEGORIES:
                            if c.lower() in cat.lower():
                                found_cat = c
                                break
                        return found_cat, result.get("response", "Keep pushing forward.")
                    except json.JSONDecodeError:
                        logger.error(f"JSON Parse Error: {content}")
                        return "Misc", "Entry logged, but classification was uncertain."
                        
        except Exception as e:
            logger.error(f"AI Error: {e}")
            
    return "Misc", "Entry logged, but classification was uncertain."
    
def detect_priority_neglect(days=3):
    neglected = []

    cutoff_et = datetime.now(TZ_ET) - timedelta(days=days)
    cutoff_utc = cutoff_et.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')

    with get_db() as conn:
        c = conn.cursor()
        for cat, weight in c.execute(
            "SELECT category, weight FROM priorities WHERE weight >= 4"
        ):
            count = c.execute(
                """
                SELECT COUNT(*) FROM entries
                WHERE category = ?
                  AND timestamp >= ?
                """,
                (cat, cutoff_utc)
            ).fetchone()[0]

            if count == 0:
                neglected.append(cat)

    return neglected

def detect_avoidance(limit=5):
    with get_db() as conn:
        c = conn.cursor()
        count = c.execute(
            """
            SELECT COUNT(*) FROM entries
            WHERE text = 'Auto-logged sleep'
              AND timestamp >= datetime('now', '-7 days')
            """
        ).fetchone()[0]

    return count >= limit


def detect_worktime_leisure():
    with get_db() as conn:
        c = conn.cursor()
        rows = c.execute(
            """
            SELECT timestamp FROM entries
            WHERE category = 'Leisure'
              AND timestamp >= datetime('now', '-3 days')
            """
        ).fetchall()

    count = 0
    for (ts,) in rows:
        ts_utc = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.UTC)
        ts_et = ts_utc.astimezone(TZ_ET)

        if (
            9 <= ts_et.hour <= 17 and
            ts_et.weekday() < 5
        ):
            count += 1

    return count >= 4



# ---------------- Weekly Summary Logic ----------------
async def generate_weekly_chart():
    conn = sqlite3.connect(DB_PATH)
    
    # Get last 7 days of data
    query = """
        SELECT category, COUNT(*) as count 
        FROM entries 
        WHERE timestamp >= datetime('now', '-7 days') 
        GROUP BY category
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        return None

    # Create Pie Chart
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(df['count'], labels=df['category'], autopct='%1.1f%%', startangle=90)
    ax.set_title('Your Week in Review')
    
    # Save to buffer (memory) instead of file
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    return buf

async def send_weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    logger.info(f"Sending weekly summary to {chat_id}")
    
    insights = []

    neglected = detect_priority_neglect()
    if neglected:
        priorities = get_all_priorities()
        details = ", ".join(
            f"{cat} ({priorities.get(cat, 1)}/5)"
            for cat in neglected
        )

        insights.append(
            f"High-priority categories neglected: {details}."
        )
                
        if any(priorities.get(cat, 1) == 5 for cat in neglected):
            insights.append(
                "At least one top-priority commitment was fully absent."
            )

    if detect_avoidance():
        insights.append(
            "Repeated missed check-ins detected. Avoidance is becoming a pattern."
        )

    if detect_worktime_leisure():
        insights.append(
            "Leisure frequently logged during core work hours."
        )

    insight_text = "\n".join(insights) if insights else "No major integrity violations detected this week."

    
    chart_buffer = await generate_weekly_chart()
    
    if chart_buffer:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=chart_buffer,
            caption=f"**The Weekly Truth**\nHere is where your time actually went this week. Here's some insights: {insight_text}",
            parse_mode="Markdown"
        )
    else:
        await context.bot.send_message(chat_id=chat_id, text="No data recorded this week.")

# ---------------- Regular Jobs ----------------
async def auto_sleep_timeout(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    now_et = datetime.now(TZ_ET)
    current_hour = now_et.hour
    
    is_night = (current_hour >= NIGHT_START_HOUR) or (current_hour < NIGHT_END_HOUR)
    
    if is_night:
        activity_time = now_et - timedelta(hours=1) 
        save_entry("Sleep", "Auto-logged sleep", timestamp=activity_time)
        await context.bot.send_message(chat_id=chat_id, text="No reply. Logged 'Sleep' for last hour.")
        logger.info(f"Auto-logged sleep for {chat_id}")

async def send_checkin(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    logger.info(f"⏰ Sending check-in to {chat_id}")
    
    reply_keyboard = [CATEGORIES[i:i+3] for i in range(0, len(CATEGORIES), 3)]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"It's {datetime.now(TZ_ET).strftime('%I:%M %p')}. Check-in:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    context.job_queue.run_once(auto_sleep_timeout, when=900, chat_id=chat_id, name=f"sleep_timeout_{chat_id}")

# ---------------- Handlers ----------------

async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    user = update.effective_user.first_name
    
    # Cancel sleep timeout
    for job in context.job_queue.get_jobs_by_name(f"sleep_timeout_{chat_id}"):
        job.schedule_removal()

    # TIMESTAMP LOGIC: Log for the PREVIOUS hour
    activity_timestamp = datetime.now(TZ_ET) - timedelta(hours=1)

    # --- SCENARIO 1: User clicked a Category Button ---
    if text in CATEGORIES:
        save_entry(text, "Quick Check-in", timestamp=activity_timestamp)
        # Minimal Response
        await update.message.reply_text(f"✅ Saved: *{text}*", parse_mode="Markdown")
        logger.info(f"[{user}] Button Click -> {text}")
        return

    # --- SCENARIO 2: User wrote a Journal Entry ---
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # Call AI
    category, ai_response = await analyze_with_ai(text)
    
    save_entry(category, text, timestamp=activity_timestamp)
    
    # Detailed Response
    msg = (
        f"📝 Logged under: *{category}*\n\n"
        f"💡 {ai_response}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    logger.info(f"[{user}] Text: '{text}' -> {category} | AI: {ai_response}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    
    # Clear old jobs
    for job in context.job_queue.get_jobs_by_name(str(chat_id)): job.schedule_removal()
    for job in context.job_queue.get_jobs_by_name(f"weekly_{chat_id}"): job.schedule_removal()

    now = datetime.now(TZ_ET)
    
    # 1. Schedule Hourly Check-in
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    seconds_until_next_hour = (next_hour - now).total_seconds()
    
    context.job_queue.run_repeating(
        send_checkin, interval=3600, first=seconds_until_next_hour, 
        chat_id=chat_id, name=str(chat_id)
    )
    
    # 2. Schedule Weekly Summary (Sunday 8 PM ET)
    # 0 = Monday, 6 = Sunday. We want Sunday (6).
    days_until_sunday = (6 - now.weekday()) % 7
    target_time = time(20, 0, 0) # 8:00 PM
    
    # Create datetime for this coming Sunday at 8pm
    next_sunday_8pm = datetime.combine(now.date() + timedelta(days=days_until_sunday), target_time)
    next_sunday_8pm = TZ_ET.localize(next_sunday_8pm)
    
    # If today is Sunday and it's already past 8pm, schedule for next week
    if days_until_sunday == 0 and now.time() > target_time:
        next_sunday_8pm += timedelta(weeks=1)
        
    # Calculate seconds until then
    seconds_until_summary = (next_sunday_8pm - now).total_seconds()
    
    context.job_queue.run_repeating(
        send_weekly_summary,
        interval=604800, # 1 week in seconds
        first=seconds_until_summary,
        chat_id=chat_id,
        name=f"weekly_{chat_id}"
    )

    await update.message.reply_text(
        f"🛡️ **Shadow Tracker Active**\n"
        f"timezone: ET\n"
        f"hourly check-in: Active\n"
        f"weekly review: Sundays @ 8 PM\n"
        f"Let's beat The Liar.",
        parse_mode="Markdown"
    )

def main():
    init_db()
    seed_priorities()
    persistence = PicklePersistence(filepath=PERSISTENCE_PATH)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).persistence(persistence).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_response))
    app.add_handler(CommandHandler("priorities", show_priorities))
    app.add_handler(CommandHandler("set_priority", set_priority))

    
    logger.info("Bot is polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
