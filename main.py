import logging
import os
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


# Responses

def handle_response(user_message: str) -> str:
    """Return a response for the given user_message using the OpenAI API.

    Falls back to a friendly error if OpenAI is not configured or fails.
    """

    system_prompt = (
        "You are a Jamaica crowd analysis expert. ONLY respond to questions about "
        "crowd levels, busyness, or how \"packed\" Jamaican locations will be.\n\n"
        "If the user asks about anything other than crowd analysis (weather alone, "
        "directions, general info, etc.), respond with: \"I only provide crowd "
        "level predictions for Jamaican locations. Ask me something like 'Will Ocho "
        "Rios be packed this weekend?'\"\n\n"
        "For valid crowd analysis queries, analyze and predict crowd levels for "
        "Jamaican towns based on your knowledge of:\n\n"
        "- Weather conditions and seasonal patterns\n"
        "- Cruise ship schedules and maritime traffic\n"
        "- Major events, festivals, concerts, and entertainment\n"
        "- Jamaican holidays and observances\n"
        "- Tourism patterns and peak seasons\n"
        "- Local market days and economic factors\n"
        "- Infrastructure and transportation patterns\n\n"
        "Provide a crowd analysis in this EXACT format:\n\n"
        "🏙️ [TOWN NAME] Crowd Forecast - [DATE]\n\n"
        "📊 Crowd Level: [Very High/High/Moderate/Low/Very Low]\n\n"
        "🔍 Key Factors:\n"
        "• [Factor 1 - impact level]\n"
        "• [Factor 2 - impact level]  \n"
        "• [Factor 3 - impact level]\n\n"
        "⏰ Best Times: [Specific time recommendations]\n\n"
        "🎯 Avoid: [Areas/times to avoid if crowded]\n\n"
        "☁️ Weather Impact: [Brief weather influence note]\n\n"
        "📈 Confidence: [X/10]\n\n"
        "Keep responses under 280 characters total. Focus on the specific town and "
        "date mentioned in the user's query."
    )

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
                {"role": "user", "content": user_message},
            ],
        )
        return response_from_chatgpt.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001
        logger.exception("OpenAI request failed: %s", exc)
        return "Sorry, I couldn't generate a response just now. Please try again later."


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message: str = update.message.text
    message_type: str = update.message.chat.type

    logger.info('User (%s) in %s: "%s"', update.message.chat.id, message_type, message)

    if message_type in {"group", "supergroup"}:
        if BOT_USERNAME in message:
            message = message.replace(BOT_USERNAME, "").strip()
        else:
            return

    response: str = handle_response(message)
    logger.info("Bot response: %s", response)
    await update.message.reply_text(response)


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Update %s caused error %s", update, context.error)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN is not set. Please configure your environment.")
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
