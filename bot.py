import os
import logging
import requests
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# --- CONFIGURATION: READ KEYS FROM THE ENVIRONMENT ---
# This correctly reads the secret keys you set in the Railway "Variables" tab.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
FACESWAP_API_KEY = os.environ.get("FACESWAP_API_KEY")

# --- API URL ---
# This is the last known correct URL for the API service.
FACESWAP_API_URL = "https://api.market/api/faceswap/v2/image/run"

# --- BOT SETUP ---
# Standard logging setup to see bot activity.
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define the states for our conversation.
WAITING_FOR_SOURCE_IMAGE, WAITING_FOR_TARGET_IMAGE = range(2)


# --- BOT FUNCTIONS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation when the user sends /swap."""
    await update.message.reply_text(
        "👋 Welcome! Let's swap some faces.\n\n"
        "First, please send the **SOURCE image** (the one with the face you want to USE)."
    )
    return WAITING_FOR_SOURCE_IMAGE


async def received_source_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the first image and asks for the second."""
    context.user_data['source_file_id'] = update.message.photo[-1].file_id
    logger.info(f"User {update.effective_user.id} provided source image.")
    await update.message.reply_text(
        "👍 Got it! Now, please send the **TARGET image** (the one you want the face put onto)."
    )
    return WAITING_FOR_TARGET_IMAGE


async def received_target_image_and_swap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the second image, calls the API, and returns the result."""
    user = update.message.from_user
    await update.message.reply_text("⏳ Processing... Please wait a moment while the magic happens!")
    try:
        # Get file paths for both images from Telegram's servers.
        source_file_id = context.user_data['source_file_id']
        source_file = await context.bot.get_file(source_file_id)
        source_image_url = source_file.file_path

        target_file_id = update.message.photo[-1].file_id
        target_file = await context.bot.get_file(target_file_id)
        target_image_url = target_file.file_path

        logger.info(f"User {user.id}: Calling the FaceSwap API.")
        
        # Prepare the request for the face swap service.
        headers = {'x-magicapi-key': FACESWAP_API_KEY}
        data = {'swap_url': source_image_url, 'target_url': target_image_url}

        # Make the API call.
        response = requests.post(FACESWAP_API_URL, headers=headers, data=data)
        response.raise_for_status()  # Checks for HTTP errors like 404 or 500.

        api_result = response.json()

        # Process the API response and send the final image back.
        if response.status_code == 200 and api_result.get('new_image_url'):
            result_image_url = api_result['new_image_url']
            logger.info(f"User {user.id}: Success! Sending the final image.")
            await update.message.reply_photo(
                photo=result_image_url,
                caption="✅ Success! Here is your swapped image."
            )
        else:
            error_message = api_result.get('message', 'Unknown API error.')
            logger.error(f"API Error for user {user.id}: {error_message}")
            await update.message.reply_text(f"❌ Sorry, the API returned an error: {error_message}")

    except Exception as e:
        logger.error(f"An unexpected error occurred for user {user.id}: {e}")
        await update.message.reply_text("❌ An unexpected error occurred. Please try again by sending /swap.")
    
    finally:
        # Clean up user data to free memory.
        context.user_data.clear()

    # End the conversation.
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current operation."""
    context.user_data.clear()
    await update.message.reply_text("Operation cancelled. Send /swap to start over.")
    return ConversationHandler.END


def main() -> None:
    """The main function that sets up and runs the bot."""
    # Build the application.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Set up the ConversationHandler for the multi-step /swap command.
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("swap", start_command)],
        states={
            WAITING_FOR_SOURCE_IMAGE: [MessageHandler(filters.PHOTO, received_source_image)],
            WAITING_FOR_TARGET_IMAGE: [MessageHandler(filters.PHOTO, received_target_image_and_swap)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )

    # Add the conversation handler to the bot.
    application.add_handler(conv_handler)

    # Add the simple /hello test command.
    async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Hello! The bot is responding from the cloud!")
    application.add_handler(CommandHandler("hello", hello))

    # Run the bot. The `drop_pending_updates=True` is the crucial fix for stability.
    print("Bot is running from the cloud...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()