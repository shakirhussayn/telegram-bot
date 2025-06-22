import os
import logging
import requests
import asyncio
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
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY")

# API URLs
FACESWAP_SUBMIT_URL = "https://api.market/api/faceswap/image/run"
FACESWAP_STATUS_URL = "https://api.market/api/faceswap/image/status"
IMGBB_UPLOAD_URL = "https://api.imgbb.com/1/upload"

# --- LOGGING SETUP ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_SOURCE_IMAGE, WAITING_FOR_TARGET_IMAGE = range(2)


async def upload_image_to_imgbb(image_data: bytes) -> str:
    """
    Upload image to ImgBB and return the direct URL.
    """
    try:
        if not IMGBB_API_KEY:
            logger.error("IMGBB_API_KEY not found in environment variables")
            return None
        
        # Convert image to base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        
        # Prepare the request - using form data as recommended
        data = {
            'key': IMGBB_API_KEY,
            'image': image_b64,
            'expiration': 900  # 15 minutes (enough time for processing)
        }
        
        # Make the request
        response = requests.post(IMGBB_UPLOAD_URL, data=data)
        
        logger.info(f"ImgBB Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                # Return the direct image URL
                image_url = result['data']['url']
                logger.info(f"Image uploaded successfully: {image_url}")
                return image_url
            else:
                logger.error(f"ImgBB upload failed: {result}")
                return None
        else:
            logger.error(f"ImgBB upload failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error uploading image to ImgBB: {e}")
        return None


async def submit_faceswap_job(swap_image_url: str, target_image_url: str) -> str:
    """Submit face swap job and return job ID."""
    try:
        headers = {
            'x-magicapi-key': FACESWAP_API_KEY,
            'Content-Type': 'application/json'
        }
        
        payload = {
            "input": {
                "swap_image": swap_image_url,
                "target_image": target_image_url
            }
        }
        
        logger.info(f"Submitting job with payload: {payload}")
        
        response = requests.post(FACESWAP_SUBMIT_URL, headers=headers, json=payload)
        
        logger.info(f"Submit API Response: {response.status_code}")
        logger.info(f"Submit API Response Body: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('id')
            logger.info(f"Job submitted successfully with ID: {job_id}")
            return job_id
        else:
            logger.error(f"Failed to submit job: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error submitting face swap job: {e}")
        return None


async def check_faceswap_status(job_id: str) -> dict:
    """Check the status of a face swap job."""
    try:
        headers = {
            'x-magicapi-key': FACESWAP_API_KEY
        }
        
        url = f"{FACESWAP_STATUS_URL}/{job_id}"
        response = requests.get(url, headers=headers)
        
        logger.info(f"Status check for {job_id}: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Status response: {result}")
            return result
        else:
            logger.error(f"Failed to check status: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error checking job status: {e}")
        return None


async def wait_for_completion(job_id: str, update_callback=None, max_wait_time: int = 180) -> dict:
    """Poll the API until the job is complete or timeout."""
    start_time = asyncio.get_event_loop().time()
    check_count = 0
    
    while True:
        check_count += 1
        current_time = asyncio.get_event_loop().time()
        elapsed_time = current_time - start_time
        
        # Check if we've exceeded max wait time
        if elapsed_time > max_wait_time:
            logger.error(f"Job {job_id} timed out after {max_wait_time} seconds")
            return None
        
        # Check job status
        status_result = await check_faceswap_status(job_id)
        
        if not status_result:
            logger.error(f"Failed to get status for job {job_id}")
            return None
        
        status = status_result.get('status', '').upper()
        logger.info(f"Job {job_id} status check #{check_count}: {status}")
        
        # Update user with progress
        if update_callback and check_count % 5 == 0:  # Update every 5th check
            minutes_elapsed = int(elapsed_time // 60)
            seconds_elapsed = int(elapsed_time % 60)
            await update_callback(
                f"⏳ Still processing... ({minutes_elapsed}m {seconds_elapsed}s)\n"
                f"Status: {status}\n"
                f"Job ID: {job_id[:8]}..."
            )
        
        if status == 'COMPLETED':
            logger.info(f"Job {job_id} completed successfully")
            return status_result
        elif status in ['FAILED', 'CANCELLED', 'ERROR']:
            logger.error(f"Job {job_id} failed with status: {status}")
            return None
        elif status in ['IN_QUEUE', 'IN_PROGRESS', 'PROCESSING', 'PENDING']:
            # Wait before checking again
            await asyncio.sleep(5)  # Check every 5 seconds
        else:
            logger.warning(f"Unknown status for job {job_id}: {status}")
            await asyncio.sleep(5)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the face swap conversation."""
    await update.message.reply_text(
        "👋 Welcome to FaceSwap Bot!\n\n"
        "🔄 **How it works:**\n"
        "1. Send me the **SOURCE image** (face to use)\n"
        "2. Send me the **TARGET image** (where to place the face)\n"
        "3. Wait 1-3 minutes for processing\n"
        "4. Get your amazing result! ✨\n\n"
        "📸 **First, send the SOURCE image** (the face you want to use for swapping).\n"
        "Make sure the face is clearly visible!"
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
        
        # Upload to ImgBB
        processing_msg = await update.message.reply_text("📤 Uploading source image...")
        
        image_url = await upload_image_to_imgbb(bytes(image_data))
        
        if not image_url:
            await processing_msg.edit_text(
                "❌ Failed to upload image. Please try again or use a different image.\n"
                "Make sure your image is under 32MB and in a supported format (JPG, PNG, etc.)"
            )
            return WAITING_FOR_SOURCE_IMAGE
        
        # Store in user context
        context.user_data['source_image_url'] = image_url
        
        await processing_msg.edit_text(
            "✅ Source image uploaded successfully!\n\n"
            "📸 Now send the **TARGET image** (where you want to place the face)."
        )
        
        logger.info(f"User {update.effective_user.id} provided source image: {image_url}")
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
    processing_msg = None
    
    try:
        # Get target image
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        target_image_data = await file.download_as_bytearray()
        
        # Upload target image
        processing_msg = await update.message.reply_text("📤 Uploading target image...")
        
        target_image_url = await upload_image_to_imgbb(bytes(target_image_data))
        
        if not target_image_url:
            await processing_msg.edit_text(
                "❌ Failed to upload target image. Please try again."
            )
            return WAITING_FOR_TARGET_IMAGE
        
        # Submit face swap job
        await processing_msg.edit_text("🚀 Submitting face swap job...")
        
        job_id = await submit_faceswap_job(
            context.user_data['source_image_url'], 
            target_image_url
        )
        
        if not job_id:
            await processing_msg.edit_text(
                "❌ Failed to submit face swap job. Please try again with /swap.\n"
                "Make sure both images contain clear, visible faces."
            )
            return ConversationHandler.END
        
        logger.info(f"User {user.id}: Face swap job submitted with ID: {job_id}")
        
        # Create update callback for progress updates
        async def update_progress(message):
            try:
                await processing_msg.edit_text(message)
            except Exception as e:
                logger.warning(f"Failed to update progress message: {e}")
        
        # Initial processing message
        await processing_msg.edit_text(
            f"⏳ Processing face swap...\n"
            f"Job ID: {job_id[:8]}...\n"
            f"This usually takes 1-3 minutes. Please be patient! ⏰"
        )
        
        # Wait for completion with progress updates
        result = await wait_for_completion(job_id, update_progress)
        
        if result and result.get('output'):
            # Handle the result
            output = result['output']
            result_image_url = None
            
            # Try different possible output formats
            if isinstance(output, str):
                if output.startswith('http'):
                    result_image_url = output
                else:
                    # Might be base64 or other format
                    logger.info(f"Output is string but not URL: {output[:100]}...")
            elif isinstance(output, dict):
                # Look for common image URL keys
                for key in ['image_url', 'url', 'result_url', 'output_url']:
                    if key in output:
                        result_image_url = output[key]
                        break
                
                if not result_image_url:
                    logger.error(f"No image URL found in output dict: {output}")
            
            if result_image_url:
                try:
                    # Download and send the result
                    result_response = requests.get(result_image_url, timeout=30)
                    if result_response.status_code == 200:
                        await processing_msg.delete()
                        await update.message.reply_photo(
                            photo=BytesIO(result_response.content),
                            caption="✅ Face swap completed successfully! 🎉\n\nHope you like the result!"
                        )
                        logger.info(f"User {user.id}: Face swap successful.")
                    else:
                        await processing_msg.edit_text(
                            f"❌ Failed to download result image.\n"
                            f"You can try accessing it directly: {result_image_url}"
                        )
                except Exception as e:
                    logger.error(f"Error downloading result: {e}")
                    await processing_msg.edit_text(
                        f"❌ Error downloading result.\n"
                        f"Direct link: {result_image_url}"
                    )
            else:
                await processing_msg.edit_text(
                    f"❌ Received result but couldn't find image URL.\n"
                    f"Raw output: {str(output)[:200]}..."
                )
        else:
            await processing_msg.edit_text(
                "❌ Face swap failed or timed out.\n\n"
                "**Possible reasons:**\n"
                "• No clear faces detected in images\n"
                "• Images too blurry or dark\n"
                "• API service temporarily unavailable\n\n"
                "Please try again with different images that have clear, visible faces."
            )
            
    except Exception as e:
        logger.error(f"Error during face swap for user {user.id}: {e}")
        if processing_msg:
            try:
                await processing_msg.edit_text(
                    "❌ An unexpected error occurred during processing.\n"
                    "Please try again with /swap."
                )
            except:
                await update.message.reply_text(
                    "❌ An unexpected error occurred during processing.\n"
                    "Please try again with /swap."
                )
        else:
            await update.message.reply_text(
                "❌ An unexpected error occurred during processing.\n"
                "Please try again with /swap."
            )
    
    finally:
        # Clean up user data
        context.user_data.clear()
    
    return ConversationHandler.END


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
4. Wait for processing (1-3 minutes)
5. Receive your swapped image! ✨

**Tips for best results:**
• Use clear, high-quality images
• Make sure faces are clearly visible
• Avoid blurry, dark, or low-resolution images
• Images should be under 32MB
• Supported formats: JPG, PNG, GIF, BMP, WEBP

**Processing time:**
Face swapping usually takes 1-3 minutes. Please be patient!

**Note:** Images are temporarily uploaded for processing and automatically deleted after 15 minutes.
    """
    await update.message.reply_text(help_text)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows bot status and API connectivity."""
    try:
        # Test API connectivity
        headers = {'x-magicapi-key': FACESWAP_API_KEY}
        
        # Try a simple request to check if API is accessible
        test_response = requests.get(
            f"{FACESWAP_STATUS_URL}/test", 
            headers=headers, 
            timeout=10
        )
        
        api_status = "✅ Connected" if test_response.status_code in [200, 404] else "❌ Error"
        
    except Exception as e:
        api_status = f"❌ Error: {str(e)[:50]}..."
    
    status_text = f"""
🤖 **Bot Status**

**API Status:** {api_status}
**Bot:** ✅ Running
**ImgBB:** {'✅ Configured' if IMGBB_API_KEY else '❌ Not configured'}

**Environment:**
• Telegram Bot: {'✅' if TELEGRAM_BOT_TOKEN else '❌'}
• FaceSwap API: {'✅' if FACESWAP_API_KEY else '❌'}
• Image Upload: {'✅' if IMGBB_API_KEY else '❌'}

Use /help for usage instructions.
    """
    
    await update.message.reply_text(status_text)


def main() -> None:
    """Main function to run the bot."""
    # Check required environment variables
    required_vars = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "FACESWAP_API_KEY": FACESWAP_API_KEY,
        "IMGBB_API_KEY": IMGBB_API_KEY
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   • {var}")
        print("\n📝 Setup instructions:")
        print("   • TELEGRAM_BOT_TOKEN: Get from @BotFather on Telegram")
        print("   • FACESWAP_API_KEY: Get from api.market")
        print("   • IMGBB_API_KEY: Get free API key from https://api.imgbb.com/")
        return
    
    logger.info("All environment variables configured ✅")
    
    # Build application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Set up conversation handler for face swap
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
    
    # Add all handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # Welcome command (same as help)
    application.add_handler(CommandHandler("start", help_command))
    
    # Test command for debugging
    async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 Hello! FaceSwap Bot is running!\n\n"
            "Use /swap to start face swapping or /help for instructions."
        )
    
    application.add_handler(CommandHandler("hello", hello))
    
    # Handle non-command messages
    async def handle_random_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 Hi! I'm a face swap bot.\n\n"
            "Use /swap to start swapping faces or /help for more information!"
        )
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_random_message))
    
    # Error handler
    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log errors and notify user."""
        logger.error(f"Update {update} caused error {context.error}")
        
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An unexpected error occurred. Please try again or contact support."
            )
    
    application.add_error_handler(error_handler)
    
    # Run the bot
    logger.info("🚀 Starting FaceSwap bot...")
    print("🤖 FaceSwap Bot is starting...")
    print("📱 Bot commands available:")
    print("   • /swap - Start face swapping")
    print("   • /help - Show help")
    print("   • /status - Check bot status")
    print("   • /cancel - Cancel operation")
    
    try:
        application.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        print("\n👋 Bot stopped gracefully")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        print(f"\n❌ Bot crashed: {e}")


if __name__ == "__main__":
    main()
