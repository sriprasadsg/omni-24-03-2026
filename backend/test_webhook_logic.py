import asyncio
import unittest
from unittest.mock import MagicMock, patch
from intent_parser_service import IntentParserService

class TestWebhookLogic(unittest.IsolatedAsyncioTestCase):
    async def test_jira_intent_parsing(self):
        print("[Test] Testing Jira Intent Parsing...")
        service = IntentParserService()
        
        # Mock payload
        payload = {
            "issue": {
                "key": "PATCH-101",
                "fields": {
                    "summary": "Install Notepad++ on HR-WS-01",
                    "description": "Please install Notepad++."
                }
            }
        }
        
        # Mock AI detection to avoid actual API calls
        with patch.object(service, '_detect_intent', return_value={
            "action": "install_software",
            "params": {"package_name": "Notepad++"},
            "target_agent": "HR-WS-01",
            "confidence": 0.9
        }):
            with patch('celery_app.celery_app.send_task') as mock_send:
                mock_send.return_value = MagicMock(id="mock-task-id")
                
                result = await service.parse_and_dispatch(payload, "jira")
                
                self.assertTrue(result["success"])
                self.assertEqual(result["task_id"], "mock-task-id")
                self.assertEqual(result["ticket_id"], "PATCH-101")
                
                # Check if correct task was sent to Celery
                mock_send.assert_called_once()
                args, kwargs = mock_send.call_args
                self.assertEqual(args[0], "tasks.run_agent_task_async")
                self.assertEqual(kwargs['args'][0], "install_software:Notepad++")
                self.assertEqual(kwargs['args'][1], "HR-WS-01")
                
        print("[PASS] Jira Intent Parsing Test Passed!")

    async def test_zoho_intent_parsing(self):
        print("[Test] Testing Zoho Intent Parsing...")
        service = IntentParserService()
        
        # Mock payload
        payload = {
            "id": "ZD-12345",
            "subject": "Set JAVA_HOME on SRV-01",
            "description": "Set JAVA_HOME=C:\\Java"
        }
        
        # Mock AI detection
        with patch.object(service, '_detect_intent', return_value={
            "action": "set_env_variable",
            "params": {"name": "JAVA_HOME", "value": "C:\\Java"},
            "target_agent": "SRV-01",
            "confidence": 0.95
        }):
            with patch('celery_app.celery_app.send_task') as mock_send:
                mock_send.return_value = MagicMock(id="mock-task-id-2")
                
                result = await service.parse_and_dispatch(payload, "zohodesk")
                
                self.assertTrue(result["success"])
                self.assertEqual(result["task_id"], "mock-task-id-2")
                
                # Check if correct task was sent to Celery
                mock_send.assert_called_once()
                args, kwargs = mock_send.call_args
                self.assertEqual(kwargs['args'][0], "set_env:JAVA_HOME=C:\\Java")
                self.assertEqual(kwargs['args'][1], "SRV-01")
                
        print("[PASS] Zoho Intent Parsing Test Passed!")

if __name__ == "__main__":
    unittest.main()
