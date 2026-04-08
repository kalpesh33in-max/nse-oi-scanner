import os
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from dotenv import load_dotenv
from utils import parse_15m_data
from logic import get_confirmation

# ---------------- CONFIG ---------------- #
load_dotenv()
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION_STR = os.getenv("TG_SESSION_STR")
SOURCE_BOT_RAW = os.getenv("SOURCE_BOT", "")
SOURCE_IDS = [int(i.strip()) for i in SOURCE_BOT_RAW.split(",") if i.strip()]
TARGET_BOT_ID = int(os.getenv("TARGET_BOT", 0)) 

async def main():
    # Using StringSession exactly like your dashboard scanner
    client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
    await client.start()
    
    print("🚀 Meta Delta Scanner Active | Listening for 15M/30M Bot Messages")

    @client.on(events.NewMessage(chats=SOURCE_IDS))
    async def handler(event):
        text = event.message.text
        
        # We only care about 15 MIN or 30 MIN messages for this scanner
        if "CUMULATIVE FLOW" not in text.upper():
            return

        try:
            # 1. Parse current data
            current_data = parse_15m_data(text)
            
            # 2. Compare with previous data for Confirmations
            alert_message = get_confirmation(current_data)
            
            # 3. If a signal is found, send the alert
            if alert_message:
                await client.send_message(TARGET_BOT_ID, alert_message)
                print(f"✅ DELTA ALERT SENT: {alert_message.splitlines()[0]}")
                
        except Exception as e:
            print(f"❌ Error in Meta Scanner: {e}")

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
