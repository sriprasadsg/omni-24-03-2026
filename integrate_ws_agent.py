# Script to integrate WebSocket client into agent.py

with open('agent/agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add import at the top (after other imports)
import_line = "from websocket_client import AgentWebSocketClient"

# Find the location after the imports (after line with "from capabilities import CAPABILITY_REGISTRY")
import_location = content.find("from capabilities import CAPABILITY_REGISTRY")
if import_location != -1:
    # Find the end of that line
    end_of_line = content.find('\n', import_location)
    # Insert the new import after it
    content = content[:end_of_line+1] + import_line + '\n' + content[end_of_line+1:]

# Add WebSocket client initialization in the agent loop
# Find the heartbeat loop section
main_loop_marker = "while True:"

# Find the main function's while loop (should be around line 850+)
# Look for "interval = cfg.get(" which indicates we're in the agent loop
interval_marker = 'interval = cfg.get("heartbeat_interval", 30)'

if interval_marker in content:
    # Find this line
    interval_pos = content.find(interval_marker)
    # Find the start of the while True loop before it
    # Go backwards to find "while True:"
    search_start = max(0, interval_pos - 1000)
    temp_content = content[search_start:interval_pos]
    while_pos = temp_content.rfind("while True:")
    
    if while_pos != -1:
        actual_while_pos = search_start + while_pos
        # Find the end of this line
        line_end = content.find('\n', actual_while_pos)
        
        # Add WebSocket client startup code after the while True: line
        ws_code = '''
        # Initialize and start WebSocket client for remote control
        try:
            ws_client = AgentWebSocketClient(
                server_url=cfg.get("api_base_url"),
                agent_id=capability_mgr.agent_id
            )
            ws_client.start_background()
            logger.info("✅ WebSocket remote control client started")
        except Exception as e:
            logger.warning(f"Failed to start WebSocket client: {e}")
        '''
        
        content = content[:line_end+1] + ws_code + content[line_end+1:]

# Write back
with open('agent/agent.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully integrated WebSocket client into agent.py")
