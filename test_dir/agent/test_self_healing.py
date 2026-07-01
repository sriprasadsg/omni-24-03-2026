import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add agent dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from capabilities.predictive_health import PredictiveHealthCapability

class TestSelfHealing(unittest.TestCase):
    def setUp(self):
        self.cap = PredictiveHealthCapability()

    @patch('psutil.disk_usage')
    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    def test_memory_exhaustion_trigger(self, mock_mem, mock_cpu, mock_disk):
        # Mock current metrics to be high
        mock_mem.return_value.percent = 98
        mock_cpu.return_value = 10
        mock_disk.return_value.percent = 50
        
        # Simulate high memory history
        self.cap.metrics_history['memory'].extend([98] * 15)
        
        result = self.cap.collect()
        remediation = result.get("remediation")
        
        self.assertIsNotNone(remediation, "Remediation should not be None")
        self.assertEqual(remediation['action'], 'restart_agent')
        self.assertIn("Critical Memory Usage", remediation['reason'])
        
    @patch('psutil.disk_usage')
    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    def test_cpu_throttle_trigger(self, mock_mem, mock_cpu, mock_disk):
        # Mock current metrics to be high
        mock_mem.return_value.percent = 50
        mock_cpu.return_value = 98
        mock_disk.return_value.percent = 50
        
        # Simulate high CPU history
        self.cap.metrics_history['cpu'].extend([98] * 15)
        
        result = self.cap.collect()
        remediation = result.get("remediation")
        
        self.assertIsNotNone(remediation, "Remediation should not be None")
        self.assertEqual(remediation['action'], 'throttle')
        self.assertIn("Critical CPU Usage", remediation['reason'])

    @patch('psutil.disk_usage')
    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    def test_no_remediation_needed(self, mock_mem, mock_cpu, mock_disk):
        # Normal usage
        mock_mem.return_value.percent = 50
        mock_cpu.return_value = 50
        mock_disk.return_value.percent = 50
        
        self.cap.metrics_history['cpu'].extend([50] * 15)
        self.cap.metrics_history['memory'].extend([50] * 15)
        
        result = self.cap.collect()
        remediation = result.get("remediation")
        
        self.assertIsNone(remediation)

if __name__ == '__main__':
    unittest.main()
