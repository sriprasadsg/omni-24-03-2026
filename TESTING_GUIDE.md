# Manual Testing Guide: Log Explorer & Agent Integration

## Prerequisites
- ✅ Frontend running on `http://localhost:3000`
- ✅ Backend running on `http://localhost:5000`
- ✅ Simulation agent running (361+ logs sent)
- ✅ API endpoint fixed: `/api/logs` (was `/logs`)

## Test 1: Verify Log Explorer with Simulation Agent

### Steps:
1. **Open Browser**: Navigate to `http://localhost:3000`
2. **Login**: 
   - Email: `super@omni.ai`
   - Password: `password123`

3. **Navigate to Log Explorer**:
   - Click "Log Explorer" in the sidebar
   - You should see a log list with real-time updates

4. **Verify Log Display**:
   - Check that logs appear with:
     - ✅ Timestamp
     - ✅ Severity (INFO, WARN, ERROR)
     - ✅ Service name (agent-core, network-monitor, compliance-scanner, updater)
     - ✅ Hostname: `simulation-agent-01`
     - ✅ Agent ID: `agent-569fc7e9` (or similar)
     - ✅ Message: "Simulated activity from..."

5. **Test Agent Filtering**:
   - Look for agent filter dropdown or search
   - Filter by hostname: `simulation-agent-01`
   - Verify only logs from this agent appear

6. **Test Real-Time Updates**:
   - Watch for new logs appearing every 2 seconds
   - Verify the log count increases

## Test 2: Agent Fleet Dashboard

### Steps:
1. **Navigate to Agents**:
   - Click "Agents" in the sidebar

2. **Verify Agent List**:
   - Look for `simulation-agent-01` in the list
   - Status should be: **Online** (green)
   - Platform: **Linux**
   - Version: **1.5.0**
   - IP: **10.0.0.99**

3. **View Agent Logs**:
   - Click "View Logs" button for `simulation-agent-01`
   - A modal should open showing filtered logs
   - Verify logs are specific to this agent (using agentId or hostname)

4. **Verify Flash UI Theme**:
   - Check for glassmorphism effects
   - Neon cyan/violet accents
   - Smooth animations on hover

## Test 3: Install and Run Real Agent (Optional)

### Windows Installation:
```powershell
# Navigate to agent installer
cd d:\Downloads\enterprise-omni-agent-ai-platform\backend\static

# Run the agent executable
.\omni-agent.exe
```

### Agent Configuration:
The agent will need:
- **Backend URL**: `http://localhost:5000`
- **Registration Key**: Get from Tenant settings in UI
- **Hostname**: Will auto-detect or can be specified

### Verify Real Agent:
1. After installation, check Agents page
2. New agent should appear with your machine's hostname
3. Click "View Logs" to see logs from the real agent
4. Verify logs show correct hostname and agentId

## Test 4: Multi-Agent Log Filtering

### If you have multiple agents running:
1. Go to Log Explorer
2. Verify you can see logs from all agents
3. Use agent filter to show logs from specific agent
4. Verify filtering works correctly:
   - By agentId (preferred)
   - By hostname (fallback)

## Expected Results

### ✅ Success Criteria:
- [ ] Logs appear in Log Explorer
- [ ] Logs show correct agent name/hostname
- [ ] Real-time log streaming works (new logs every 2 seconds)
- [ ] Agent filtering works correctly
- [ ] Agent appears in Fleet dashboard
- [ ] "View Logs" modal shows agent-specific logs
- [ ] Flash UI theme is applied consistently

### ❌ Common Issues:

**Issue**: No logs appearing
- **Solution**: Refresh browser (Ctrl+F5) to reload JavaScript with fixed API endpoint

**Issue**: Agent not in list
- **Solution**: Check if agent registered successfully, verify registration key

**Issue**: Logs not filtered correctly
- **Solution**: Check browser console for errors, verify agentId is present in logs

## API Verification (Fallback)

If UI testing fails, verify via API:

```powershell
# Get all logs
curl http://localhost:5000/api/logs -H "Authorization: Bearer YOUR_TOKEN"

# Get all agents
curl http://localhost:5000/api/agents -H "Authorization: Bearer YOUR_TOKEN"
```

## Notes
- The simulation script sends logs every 2 seconds
- Logs include random severity levels (INFO, WARN, ERROR)
- Each log has both `hostname` and `agentId` fields
- Frontend prioritizes `agentId` for filtering (more accurate)
