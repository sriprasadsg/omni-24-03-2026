import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os
import hashlib

# Adjust path to import the capability
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from agent.capabilities.compliance import ComplianceEnforcementCapability

class TestLinuxCompliance(unittest.TestCase):
    @patch('os.stat')
    @patch('os.listdir')
    @patch('platform.system', return_value='Linux')
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_linux_evidence_collection(self, mock_exists, mock_file, mock_subprocess, mock_platform, mock_listdir, mock_stat):
        # Setup mocks
        mock_exists.return_value = True
        mock_listdir.return_value = ['job1']
        
        mock_stat_obj = MagicMock()
        mock_stat_obj.st_uid = 0
        mock_stat_obj.st_gid = 0
        mock_stat_obj.st_mode = 0o600
        mock_stat.return_value = mock_stat_obj
        
        # Mock subprocess outputs for various commands
        def subprocess_side_effect(command, capture_output=True, text=True, check=False, **kwargs):
            cmd_str = command if isinstance(command, str) else ' '.join(command)
            result = MagicMock()
            result.returncode = 0
            
            if "ufw status" in cmd_str:
                result.stdout = "Status: active"
            elif "systemctl is-active snapd.auto-import.service" in cmd_str:
                 result.stdout = "active"
            elif "sestatus" in cmd_str:
                result.stdout = "SELinux status: enabled"
            elif "getenforce" in cmd_str:
                result.stdout = "Enforcing"
            elif "crontab -l" in cmd_str:
                result.stdout = "0 0 * * * /backup.sh"
            elif "ls -l /etc/shadow" in cmd_str:
                result.stdout = "-rw-r----- 1 root shadow 1000 Jan 1 00:00 /etc/shadow"
            else:
                result.stdout = "Generic Output"
            
            return result
            
        mock_subprocess.side_effect = subprocess_side_effect
        
        # Mock file contents
        file_contents = {
            "/etc/ssh/ssh_config": "Protocol 2",
            "/etc/sudoers": "root ALL=(ALL:ALL) ALL",
            "/etc/ssh/sshd_config": "PermitRootLogin no"
        }
        
        def open_side_effect(file, mode='r', *args, **kwargs):
            content = file_contents.get(file, "Generic File Content")
            file_obj = mock_open(read_data=content).return_value
            file_obj.__enter__.return_value = file_obj
            return file_obj

        mock_file.side_effect = open_side_effect

        # Instantiate capability
        capability = ComplianceEnforcementCapability()
        
        # Run checks (we can access the private method for testing purposes)
        checks = capability._linux_compliance_checks()
        
        # Verify Evidence
        found_ufw = False
        found_ssh = False
        
        print("\n--- Compliance Checks Evidence Verification ---\n")
        
        for check in checks:
            print(f"Check: {check.get('check')}")
            print(f"Status: {check.get('status')}")
            evidence = check.get('evidence_content')
            content_hash = check.get('content_hash')
            print(f"Evidence: {evidence}")
            print(f"Hash: {content_hash}")
            print("-" * 30)
            
            if check.get('check') == "UFW Firewall Enabled":
                self.assertEqual(evidence, "Status: active")
                self.assertIsNotNone(content_hash)
                expected_hash = hashlib.sha256(evidence.encode('utf-8')).hexdigest()
                self.assertEqual(content_hash, expected_hash)
                found_ufw = True
                
            if check.get('check') == "SSH Root Login Disabled":
                self.assertEqual(evidence, "PermitRootLogin no")
                self.assertIsNotNone(content_hash)
                found_ssh = True

        self.assertTrue(found_ufw, "UFW check not found or tested")
        self.assertTrue(found_ssh, "SSH check not found or tested")

if __name__ == '__main__':
    unittest.main()
