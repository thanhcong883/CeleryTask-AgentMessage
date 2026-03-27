import unittest
from unittest.mock import patch, MagicMock
from telegram_service import sync_telegram_webhook

class TestTelegramSync(unittest.TestCase):
    @patch('telegram_service.requests')
    def test_sync_needed(self, mock_requests):
        # Mock getWebhookInfo to return a different URL
        mock_get_info = MagicMock()
        mock_get_info.json.return_value = {
            "ok": True,
            "result": {"url": "http://old-url.com"}
        }
        mock_get_info.status_code = 200
        
        mock_set_webhook = MagicMock()
        mock_set_webhook.json.return_value = {"ok": True, "description": "Webhook was set"}
        mock_set_webhook.status_code = 200

        mock_requests.get.return_value = mock_get_info
        mock_requests.post.return_value = mock_set_webhook

        bot_id = "test_bot"
        token = "test_token"
        base_url = "https://new-url.com"
        
        result = sync_telegram_webhook(bot_id, token, base_url)
        
        # Verify setWebhook was called
        expected_webhook_url = f"{base_url}/api/hook?platform=telegram&bot_id={bot_id}"
        mock_requests.post.assert_called_once_with(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": expected_webhook_url},
            timeout=10
        )
        self.assertEqual(result, {"ok": True, "message": "Webhook set successfully", "url": expected_webhook_url})

    @patch('telegram_service.requests')
    def test_sync_already_correct(self, mock_requests):
        bot_id = "test_bot"
        token = "test_token"
        base_url = "https://correct-url.com"
        webhook_url = f"{base_url}/api/hook?platform=telegram&bot_id={bot_id}"

        mock_get_info = MagicMock()
        mock_get_info.json.return_value = {
            "ok": True,
            "result": {"url": webhook_url}
        }
        mock_get_info.status_code = 200
        mock_requests.get.return_value = mock_get_info

        result = sync_telegram_webhook(bot_id, token, base_url)
        
        # Verify setWebhook was NOT called
        mock_requests.post.assert_not_called()
        self.assertEqual(result, {"ok": True, "message": "Already synced", "url": webhook_url})

    @patch('telegram_service.requests')
    def test_sync_double_slash_bug(self, mock_requests):
        bot_id = "test_bot"
        token = "test_token"
        base_url = "https://correct-url.com/" # Trailing slash
        
        # This will construct https://correct-url.com//api/hook...
        expected_webhook_url = f"{base_url}api/hook?platform=telegram&bot_id={bot_id}"
        
        mock_get_info = MagicMock()
        mock_get_info.json.return_value = {
            "ok": True,
            "result": {"url": expected_webhook_url}
        }
        mock_get_info.status_code = 200
        mock_requests.get.return_value = mock_get_info

        # In current implementation, if base_url has trailing slash, it will match
        # BUT if sync_telegram_webhook is called with "https://correct-url.com/" 
        # and Telegram has "https://correct-url.com/api/hook..." (single slash), it won't match.
        
        # Set up current state with single slash
        actual_webhook_url = "https://correct-url.com/api/hook?platform=telegram&bot_id=test_bot"
        mock_get_info.json.return_value = {
            "ok": True,
            "result": {"url": actual_webhook_url}
        }
        
        mock_set_webhook = MagicMock()
        mock_set_webhook.json.return_value = {"ok": True}
        mock_requests.post.return_value = mock_set_webhook

        sync_telegram_webhook(bot_id, token, base_url)
        
        # If it handles trailing slash, it will match the existing single slash URL
        # and NOT call setWebhook.
        mock_requests.post.assert_not_called()

if __name__ == '__main__':
    unittest.main()
