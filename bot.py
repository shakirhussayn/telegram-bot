import os
import logging
import requests
import base64
from io import BytesIO
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
FACESWAP_API_KEY = os.environ.get("FACESWAP_API_KEY")

# Updated API URL - check the actual documentation
FACESWAP_API_URL = "https://api.market/store/magicapi/faceswap-v2"

# --- LOGGING SETUP ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_SOURCE_IMAGE, WAITING_FOR_TARGET_IMAGE = range(2)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the face swap conversation."""
    await update.message.reply_text(
        "👋 Welcome to FaceSwap Bot!\n\n"
        "First, send the **SOURCE image** (the face you want to use for swapping).\n"
        "Make sure the face is clearly visible! 📸"
    )
    return WAITING_FOR_SOURCE_IMAGE


async def received_source_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the source image."""
    try:
        # Get the highest resolution photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        # Download the image data
        image_data = await file.download_as_bytearray()
        
        # Store in user context
        context.user_data['source_image'] = image_data
        
        logger.info(f"User {update.effective_user.id} provided source image.")
        await update.message.reply_text(
            "✅ Source image received!\n\n"
            "Now send the **TARGET image** (where you want to place the face)."
        )
        return WAITING_FOR_TARGET_IMAGE
        
    except Exception as e:
        logger.error(f"Error processing source image: {e}")
        await update.message.reply_text(
            "❌ Error processing the image. Please try again with a different image."
        )
        return WAITING_FOR_SOURCE_IMAGE


async def received_target_image_and_swap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the target image and performs face swap."""
    user = update.message.from_user
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        "⏳ Processing your face swap... This may take a few moments!"
    )
    
    try:
        # Get target image
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        target_image_data = await file.download_as_bytearray()
        
        logger.info(f"User {user.id}: Starting face swap process.")
        
        # Prepare images for API
        source_b64 = base64.b64encode(context.user_data['source_image']).decode('utf-8')
        target_b64 = base64.b64encode(target_image_data).decode('utf-8')
        
        # Call the face swap API
        result_image = await call_faceswap_api(source_b64, target_b64)
        
        if result_image:
            # Delete processing message
            await processing_msg.delete()
            
            # Send the result
            await update.message.reply_photo(
                photo=BytesIO(result_image),
                caption="✅ Face swap completed! Here's your result! 🎉"
            )
            logger.info(f"User {user.id}: Face swap successful.")
        else:
            await processing_msg.edit_text(
                "❌ Face swap failed. Please try with different images that have clear, visible faces."
            )
            
    except Exception as e:
        logger.error(f"Error during face swap for user {user.id}: {e}")
        await processing_msg.edit_text(
            "❌ An error occurred during processing. Please try again with /swap."
        )
    
    finally:
        # Clean up user data
        context.user_data.clear()
    
    return ConversationHandler.END


async def call_faceswap_api(source_b64: str, target_b64: str) -> bytes:
    """
    Calls the MagicAPI FaceSwap service.
    You may need to adjust this based on the actual API documentation.
    """
    try:
        headers = {
            'Authorization': f'Bearer {FACESWAP_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Adjust payload based on actual API requirements
        payload = {
            'source_image': f'data:image/jpeg;base64,{source_b64}',
            'target_image': f'data:image/jpeg;base64,{target_b64}',
            # Add other parameters as needed
        }
        
        # Alternative payload format (try this if above doesn't work)
        # payload = {
        #     'swap_image': source_b64,
        #     'target_image': target_b64,
        #     'format': 'base64'
        # }
        
        response = requests.post(
            FACESWAP_API_URL, 
            headers=headers, 
            json=payload,
            timeout=60  # 60 second timeout
        )
        
        logger.info(f"API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            # Handle different possible response formats
            if 'result_image' in result:
                # If response contains base64 image
                if result['result_image'].startswith('data:image'):
                    image_data = result['result_image'].split(',')[1]
                else:
                    image_data = result['result_image']
                return base64.b64decode(image_data)
                
            elif 'image_url' in result:
                # If response contains URL to image
                img_response = requests.get(result['image_url'])
                return img_response.content
                
            elif 'output' in result:
                # Alternative response format
                return base64.b64decode(result['output'])
        
        else:
            logger.error(f"API Error: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("API request timed out")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in API call: {e}")
        return None


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current operation."""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Operation cancelled. Send /swap to start a new face swap!"
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows help information."""
    help_text = """
🤖 **FaceSwap Bot Help**

**Commands:**
• /swap - Start a new face swap
• /help - Show this help message
• /cancel - Cancel current operation

**How to use:**
1. Send /swap to start
2. Send the source image (face to use)
3. Send the target image (where to place face)
4. Wait for the magic! ✨

**Tips:**
• Use clear, high-quality images
• Make sure faces are clearly visible
• Avoid blurry or dark images
• Be patient - processing takes time!
    """
    await update.message.reply_text(help_text)


def main() -> None:
    """Main function to run the bot."""
    if not TELEGRAM_BOT_TOKEN or not FACESWAP_API_KEY:
        logger.error("Missing required environment variables!")
        return
    
    # Build application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Set up conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("swap", start_command)],
        states={
            WAITING_FOR_SOURCE_IMAGE: [
                MessageHandler(filters.PHOTO, received_source_image)
            ],
            WAITING_FOR_TARGET_IMAGE: [
                MessageHandler(filters.PHOTO, received_target_image_and_swap)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )
    
    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    
    # Test command
    async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("👋 Hello! Bot is running! Use /help for instructions.")
    
    application.add_handler(CommandHandler("hello", hello))
    
    # Run the bot
    logger.info("Starting bot...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
