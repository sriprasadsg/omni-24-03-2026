import subprocess
import os
import datetime
import html

# Test Configuration
TEST_SCRIPTS = [
    {
        "name": "Full System API (Auth, Dashboard, Agents)",
        "script": "verify_full_system.py",
        "description": "Verifies Core API endpoints: Login, Metrics, Agent Listing."
    },
    {
        "name": "Remote Control API",
        "script": "trigger_remote.py",
        "description": "Verifies Remote Control Command Dispatch via Socket.IO."
    },
    {
        "name": "Local LLM (Ollama)",
        "script": "test_llm.py",
        "description": "Verifies Local LLM connectivity and generation."
    }
]

REPORT_FILE = "test_report.html"

def run_script(script_name):
    """Run a python script and return (success, output)"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    try:
        result = subprocess.run(
            ["python", script_name],
            capture_output=True,
            text=True,
            timeout=60,
            encoding='utf-8',
            env=env
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def generate_html(results):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Calculate Summary
    total = len(results)
    passed = sum(1 for r in results if r['success'])
    failed = total - passed
    status_color = "green" if failed == 0 else "red"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Omni Platform Test Report</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1000px; margin: 0 auto; padding: 20px; background: #f5f7fa; }}
            .header {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; border-left: 5px solid {status_color}; }}
            .summary {{ display: flex; gap: 20px; margin-top: 10px; }}
            .metric {{ background: #f0f2f5; padding: 10px 20px; border-radius: 6px; }}
            .metric strong {{ display: block; font-size: 1.5em; }}
            .metric span {{ color: #666; font-size: 0.9em; }}
            
            .test-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 15px; }}
            .test-header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 10px; }}
            .test-title {{ font-size: 1.2em; font-weight: 600; display: flex; align-items: center; gap: 10px; }}
            .test-status {{ padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: 600; }}
            .status-pass {{ background: #e6fffa; color: #047857; }}
            .status-fail {{ background: #fef2f2; color: #dc2626; }}
            
            .logs {{ background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 6px; font-family: 'Consolas', 'Monaco', monospace; font-size: 0.9em; overflow-x: auto; white-space: pre-wrap; display: none; }}
            .toggle-logs {{ background: none; border: 1px solid #ddd; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 0.8em; margin-top: 10px; }}
            .toggle-logs:hover {{ background: #f5f5f5; }}
            
            h1 {{ margin: 0; }}
        </style>
        <script>
            function toggleLogs(id) {{
                const el = document.getElementById(id);
                el.style.display = el.style.display === 'block' ? 'none' : 'block';
            }}
        </script>
    </head>
    <body>
        <div class="header">
            <h1>🛡️ Omni Platform Verification Report</h1>
            <div class="summary">
                <div class="metric"><strong>{timestamp}</strong><span>Run Time</span></div>
                <div class="metric" style="color: {status_color}"><strong>{passed}/{total}</strong><span>Tests Passed</span></div>
            </div>
        </div>
    """
    
    for i, res in enumerate(results):
        status_class = "status-pass" if res['success'] else "status-fail"
        status_text = "PASSED" if res['success'] else "FAILED"
        log_id = f"log-{i}"
        
        # Simple heuristic check for specific success keywords in output
        # Because return code 0 might not mean logic success in python scripts sometimes
        if res['success']:
             if "Failed" in res['output'] or "Error" in res['output'] or "CRITICAL" in res['output']:
                 # Double check if these are real errors or just printed text
                 # For now trust returncode unless output strictly implies failure
                 pass

        html_content += f"""
        <div class="test-card">
            <div class="test-header">
                <div class="test-title">
                    {res['name']}
                    <span style="font-size: 0.8em; color: #666; font-weight: normal;">({res['script']})</span>
                </div>
                <div class="test-status {status_class}">{status_text}</div>
            </div>
            <p>{res['description']}</p>
            <button class="toggle-logs" onclick="toggleLogs('{log_id}')">View Logs</button>
            <div id="{log_id}" class="logs">{html.escape(res['output'])}</div>
        </div>
        """
        
    html_content += """
    </body>
    </html>
    """
    
    return html_content

def main():
    print("🚀 Generating verification report...")
    results = []
    
    for test in TEST_SCRIPTS:
        print(f"Running {test['name']}...")
        success, output = run_script(test['script'])
        
        # Heuristic: If script printed "❌", treat as fail even if exit code 0
        if "❌" in output:
            success = False
            
        results.append({
            "name": test['name'],
            "script": test['script'],
            "description": test['description'],
            "success": success,
            "output": output
        })
        print(f"  -> {'PASS' if success else 'FAIL'}")

    html_report = generate_html(results)
    
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(html_report)
        
    print(f"\n✅ Report generated: {os.path.abspath(REPORT_FILE)}")

if __name__ == "__main__":
    main()
