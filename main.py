# main.py

import asyncio
import logging
from dotenv import load_dotenv

# Import the main class from your alfred.py file
from Alfred import Alfred
# Import the Gmail authentication function to run a pre-flight check
from langchain_tools import google_authenticate, startup_browser, shutdown_browser

# Configure logging for better debugging and to see the auth flow
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# Silence overly verbose loggers from Google's libraries
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)


async def check_google_auth():
    """
    Performs a one-time authentication check for all Google services on startup.
    """
    logging.info("Performing startup check for Google services authentication...")
    try:
        # Call the renamed 'google_authenticate' function
        creds = await google_authenticate()
        if creds:
             logging.info("Google authentication successful.")
        return True
    except FileNotFoundError as e:
        logging.error(f"Authentication setup error: {e}")
        logging.warning("Google tools will not be available.")
        return False
    except Exception as e:
        logging.error(f"An error occurred during Google authentication check: {e}")
        logging.warning("There might be an issue with Google tools.")
        return False


async def main():
    """
    Main function to initialize and run the Alfred voice assistant.
    """
    logging.info("Starting Alfred...")

    # Load environment variables from your .env file
    load_dotenv()

    # --- Pre-flight Checks ---
    await check_google_auth()
    await startup_browser()

    # --- Initialize and Run Alfred ---
    alfred_instance = None
    try:
        # 1. Initialize Alfred
        alfred_instance = Alfred()
        logging.info("Alfred initialized successfully.")

        # 2. Create the concurrent tasks for Alfred's core functions
        tasks = [
            asyncio.create_task(alfred_instance.stt()),           # Speech-to-Text
            asyncio.create_task(alfred_instance.send_prompt()),   # LangGraph Agent Logic
            asyncio.create_task(alfred_instance.tts()),           # Text-to-Speech
            asyncio.create_task(alfred_instance.play_audio()),    # Audio Playback
        ]

        # 3. Run all tasks together
        await asyncio.gather(*tasks)

    except Exception as e:
        logging.critical(f"A critical error occurred in the main run function: {e}", exc_info=True)
    finally:
        logging.info("Shutting down Alfred...")
        await shutdown_browser()
        if alfred_instance and alfred_instance.pya:
            alfred_instance.pya.terminate()
            logging.info("PyAudio instance terminated.")
        logging.info("Alfred has been shut down.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by user. Exiting.")