import logging
import os
import re
import textwrap
import time
from collections import defaultdict
from typing import Final

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Load environment variables from .env if present
load_dotenv()

# Constants / configuration
BOT_USERNAME: Final = "@jampacked_bot"
TELEGRAM_TOKEN: Final | None = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY: Final | None = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL: Final = "gpt-3.5-turbo"

# Initialize OpenAI client (may be None if key missing)
client: OpenAI | None = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Simple rate limiting - track requests per user
user_request_times = defaultdict(list)
MAX_REQUESTS_PER_MINUTE = 5

logger = logging.getLogger(__name__)


# Commands
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a help/intro message to the user."""
    await update.message.reply_text(
        (
            "Wah Gwan! (Hello!). Which data and Jamaican city would you like to travel to?\n"
            "Example: Will Ochi be packed this weekend?\n\n"
            "Quick commands:\n"
            "/ochi - Check if Ocho Rios will be packed this weekend\n"
            "/mobay - Check if Montego Bay will be packed this weekend\n"
            "/negril - Check if Negril will be packed this weekend"
        )
    )


async def ochi_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    response = handle_response("Will Ocho Rios be packed this weekend?")
    await update.message.reply_text(response)


async def mobay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    response = handle_response("Will Montego Bay be packed this weekend?")
    await update.message.reply_text(response)


async def negril_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    response = handle_response("Will Negril be packed this weekend?")
    await update.message.reply_text(response)


# Input validation and sanitization

def is_rate_limited(user_id: int) -> bool:
    """Check if user has exceeded rate limit."""
    current_time = time.time()
    user_times = user_request_times[user_id]
    
    # Remove requests older than 1 minute
    user_times[:] = [t for t in user_times if current_time - t < 60]
    
    if len(user_times) >= MAX_REQUESTS_PER_MINUTE:
        return True
    
    # Add current request time
    user_times.append(current_time)
    return False


def sanitize_user_input(user_input: str) -> str | None:
    """Sanitize and validate user input before processing.
    
    Returns sanitized input or None if input is invalid.
    """
    if not user_input or not isinstance(user_input, str):
        return None
    
    # Length validation - limit to reasonable size
    if len(user_input.strip()) > 500:
        return None
    
    # Basic sanitization - remove excessive whitespace and control characters
    sanitized = re.sub(r'\s+', ' ', user_input.strip())
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', sanitized)
    
    # Check for potential injection attempts or malicious patterns
    suspicious_patterns = [
        r'(?i)system\s*prompt',
        r'(?i)ignore\s+previous',
        r'(?i)forget\s+everything',
        r'(?i)you\s+are\s+now',
        r'(?i)new\s+instructions',
        r'(?i)role\s*:\s*system',
        r'(?i)</\s*system\s*>',
        r'(?i)<\s*system\s*>',
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, sanitized):
            return None
    
    # Ensure minimum length after sanitization
    if len(sanitized) < 3:
        return None
        
    return sanitized


# Responses

def handle_response(user_message: str) -> str:
    """Return a response for the given user_message using the OpenAI API.

    Falls back to a friendly error if OpenAI is not configured or fails.
    """
    
    # Sanitize user input first
    sanitized_message = sanitize_user_input(user_message)
    if sanitized_message is None:
        return "Please send a valid message about crowd levels in Jamaica (e.g., 'Will Ocho Rios be packed this weekend?')"

    system_prompt = textwrap.dedent(
        """
        You are a Jamaica crowd analysis expert. ONLY respond to questions about
        crowd levels, busyness, or how "packed" Jamaican locations will be.

        If the user asks about anything other than crowd analysis (weather alone,
        directions, general info, etc.), respond with: "I only provide crowd
        level predictions for Jamaican locations. Ask me something like 'Will Ocho
        Rios be packed this weekend?'"

        For valid crowd analysis queries, analyze and predict crowd levels for
        Jamaican towns based on your knowledge of:

        - Weather conditions and seasonal patterns
        - Cruise ship schedules and maritime traffic
        - Major events, festivals, concerts, and entertainment
        - Jamaican holidays and observances
        - Tourism patterns and peak seasons
        - Local market days and economic factors
        - Infrastructure and transportation patterns

        Provide a crowd analysis in this EXACT format:

        🏙️ [TOWN NAME] Crowd Forecast - [DATE]

        📊 Crowd Level: [Very High/High/Moderate/Low/Very Low]

        🔍 Key Factors:
        • [Factor 1 - impact level]
        • [Factor 2 - impact level]
        • [Factor 3 - impact level]

        ⏰ Best Times: [Specific time recommendations]

        🎯 Avoid: [Areas/times to avoid if crowded]

        ☁️ Weather Impact: [Brief weather influence note]

        📈 Confidence: [X/10]

        Keep responses under 280 characters total. Focus on the specific town and
        date mentioned in the user's query.
        """
    ).strip()

    if client is None:
        logger.warning("OpenAI API key is not configured; returning fallback message.")
        return (
            "I can't reach the prediction service right now. Please set OPENAI_API_KEY "
            "and try again."
        )

    try:
        response_from_chatgpt = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": sanitized_message},
            ],
        )
        return response_from_chatgpt.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"OpenAI request failed: {exc}")
        return "Sorry, I couldn't generate a response just now. Please try again later."


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message: str = update.message.text
    message_type: str = update.message.chat.type
    user_id: int = update.message.from_user.id

    logger.info(f'User ({user_id}) in {message_type}: "{message}"')

    # Check rate limiting
    if is_rate_limited(user_id):
        await update.message.reply_text(
            "You're sending messages too quickly. Please wait a minute before trying again."
        )
        return

    if message_type in {"group", "supergroup"}:
        if BOT_USERNAME in message:
            message = message.replace(BOT_USERNAME, "").strip()
        else:
            return

    response: str = handle_response(message)
    logger.info(f"Bot response: {response}")
    await update.message.reply_text(response)


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception(f"Update {update} caused error {context.error}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    # Validate required environment variables
    missing_vars = []
    if not TELEGRAM_TOKEN:
        missing_vars.append("TELEGRAM_TOKEN")
    if not OPENAI_API_KEY:
        missing_vars.append("OPENAI_API_KEY")
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}. Please configure your environment.")
        raise SystemExit(1)

    logger.info("Starting bot ...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("ochi", ochi_command))
    app.add_handler(CommandHandler("mobay", mobay_command))
    app.add_handler(CommandHandler("negril", negril_command))

    app.add_error_handler(error)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Polling ...")
    app.run_polling(poll_interval=3)
