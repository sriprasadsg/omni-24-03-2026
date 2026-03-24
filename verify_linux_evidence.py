import unittest
import sys
import os

# Adjust path to import the test
sys.path.append(os.getcwd())

from agent.capabilities.test_linux_compliance_mock import TestLinuxCompliance

suite = unittest.TestLoader().loadTestsFromTestCase(TestLinuxCompliance)
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

if result.wasSuccessful():
    print("VERIFICATION_SUCCESS")
    sys.exit(0)
else:
    print("VERIFICATION_FAILURE")
    sys.exit(1)
