import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add agent dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from capabilities.update_capability import AgentUpdateCapability

class TestUpdateCapability(unittest.TestCase):
    def setUp(self):
        self.cap = AgentUpdateCapability()

    @patch('requests.get')
    def test_check_update_available(self, mock_get):
        # Mock response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "version": "2.1.0",
            "url": "http://test/agent.py",
            "filename": "agent.py"
        }
        mock_get.return_value = mock_resp
        
        # Mock perform_update to avoid actual update
        self.cap.perform_update = MagicMock()
        self.cap.current_version = "2.0.0"
        
        # Mock config loading
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.read_text', return_value="api_base_url: http://localhost:5000"):
            self.cap.execute()
        
        self.cap.perform_update.assert_called_once()
        
    @patch('requests.get')
    def test_check_no_update(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "version": "2.0.0",
            "url": "http://test/agent.py"
        }
        mock_get.return_value = mock_resp
        
        self.cap.perform_update = MagicMock()
        self.cap.current_version = "2.0.0"
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.read_text', return_value="api_base_url: http://localhost:5000"):
            self.cap.execute()
        
        self.cap.perform_update.assert_not_called()

if __name__ == '__main__':
    unittest.main()
