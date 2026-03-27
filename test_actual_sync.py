import logging
from telegram_service import sync_telegram_webhook, get_telegram_webhook_info


logging.basicConfig(level=logging.INFO)

token = "8685270318:AAF-9MOlE2qZ4aphAp4GpwoRZyHMaqXkpPY"
bot_id = "test_bot"
base_url = "https://example.com"

try:
    print("Testing sync_telegram_webhook with trailing slash (FIX VERIFICATION)...")
    base_url_slash = "https://example.com/"
    result = sync_telegram_webhook(bot_id, token, base_url_slash)
    print(f"Result: {result}")
    
    # Verify no double slash in the recorded URL
    info = get_telegram_webhook_info(token)
    current_url = info.get("result", {}).get("url")
    print(f"Current Webhook URL: {current_url}")
    
    if "//api/hook" in current_url:
        print("FAILURE: Double slash found in webhook URL.")
    else:
        print("SUCCESS: No double slash found in webhook URL.")
        
    # Verify consistent return value keys
    if "message" in result and "url" in result:
        print("SUCCESS: Result contains consistent keys ('message', 'url').")
    else:
        print(f"FAILURE: Result missing expected keys: {result.keys()}")

except Exception as e:
    print(f"Error: {e}")





