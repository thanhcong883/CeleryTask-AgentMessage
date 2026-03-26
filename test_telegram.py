import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def telegram_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    data = {
        "platform_name": "Telegram",
        "content": update.message.text,
        "platform_user_id": str(update.message.from_user.id),
        "platform_conv_id": str(update.message.chat_id),
        "token": context.bot.token,
        "type": "private" if update.message.chat.type == "private" else "group",
    }

    logger.info(f"Received Telegram message from {data['platform_user_id']}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and its stack trace."""
    logger.error("Exception while handling an update:", exc_info=context.error)

async def main():
    application = ApplicationBuilder().token("8685270318:AAF-9MOlE2qZ4aphAp4GpwoRZyHMaqXkpPY").build()
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), telegram_message_handler))
    application.add_error_handler(error_handler)

    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    stop_event = asyncio.Event()
    logger.info("Bot started. Press Ctrl+C to stop.")
    
    # Keep the bot running until interrupted
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopping bot...")
        stop_event.set()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())

