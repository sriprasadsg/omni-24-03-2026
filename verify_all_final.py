import subprocess
import sys
import time

TEST_SCRIPTS = [
    "test_etl_pipeline.py",
    "test_streaming.py",
    "test_governance.py",
    "test_finops.py",
    "test_mlops.py",
    "test_automl.py",
    "test_xai.py",
    "test_ab_testing.py",
    "verify_k8s_manifests.py",
    "verify_cicd_config.py"
]

def run_script(script_name):
    print(f"\n{'='*50}")
    print(f"RUNNING: {script_name}")
    print(f"{'='*50}")
    
    try:
        # Run process and capture output
        result = subprocess.run(
            [sys.executable, script_name], 
            cwd=".", 
            capture_output=True, 
            text=True, 
            timeout=60 # 60s timeout per script
        )
        
        print(result.stdout)
        
        if result.returncode == 0:
            print(f"✅ PASS: {script_name}")
            return True
        else:
            print(f"❌ FAIL: {script_name}")
            print("STDERR:", result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    print("🚀 STARTING FINAL SYSTEM VERIFICATION 🚀")
    start_time = time.time()
    
    passed = 0
    failed = 0
    
    for script in TEST_SCRIPTS:
        if run_script(script):
            passed += 1
        else:
            failed += 1
            
    duration = time.time() - start_time
    
    print(f"\n{'='*50}")
    print(f"SUMMARY REPORT")
    print(f"{'='*50}")
    print(f"Total Tests: {len(TEST_SCRIPTS)}")
    print(f"Passed:      {passed}")
    print(f"Failed:      {failed}")
    print(f"Duration:    {duration:.2f}s")
    
    if failed == 0:
        print("\n✅ SYSTEM INTEGRITY CONFIRMED")
    else:
        print("\n⚠️ SYSTEM ISSUES DETECTED")

if __name__ == "__main__":
    main()
