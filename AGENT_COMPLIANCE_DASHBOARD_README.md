# Universal Agent Compliance Dashboard

## Overview

This is a **universal HTML dashboard** that displays compliance status and evidence for **any agent** in the Omni Platform. No configuration needed - just change the agent ID!

## Features

✅ **Universal Agent Support** - Works with any agent ID  
✅ **Full Evidence Display** - View all evidence content with expand/collapse  
✅ **Real-time Search** - Filter controls by ID or evidence content  
✅ **Filter by Status** - Show all, compliant, or non-compliant controls  
✅ **Beautiful UI** - Modern gradient design with smooth animations  
✅ **No Installation** - Pure HTML/JS, works offline once loaded  

---

## Quick Start

### Method 1: Open in Browser
```powershell
# Open the dashboard
start d:\Downloads\enterprise-omni-agent-ai-platform\agent_compliance_dashboard.html
```

The dashboard will automatically load agent **EILT0197** by default.

### Method 2: URL Parameters
Open the dashboard with a specific agent:
```
file:///d:/Downloads/enterprise-omni-agent-ai-platform/agent_compliance_dashboard.html?agent=EILT0197
```

### Method 3: Use the Input Box
1. Open the dashboard
2. Type the agent ID in the input box (e.g., `SERVER-001`)
3. Click "Load Agent"

---

## Usage Guide

### Viewing Compliance Status

The dashboard shows 4 key metrics:
- **Total Controls** - Number of controls being monitored
- **Compliant** - Controls that passed all checks (green)
- **Non-Compliant** - Controls that failed checks (red)
- **Compliance Rate** - Percentage of compliant controls

### Viewing Evidence

1. **Expand a Control** - Click on any control row to expand it
2. **View Evidence** - See all evidence collected for that control
3. **Evidence Details** include:
   - Evidence name (e.g., "System Check: Windows Firewall Profiles")
   - Upload/collection timestamp
   - Full evidence content (markdown formatted)

### Search & Filter

**Search:**
- Type in the search box to filter by control ID or evidence content
- Example: Search "firewall" to see all firewall-related controls

**Filter:**
- **All** - Show all controls
- **Compliant** - Show only passing controls
- **Non-Compliant** - Show only failing controls

---

## For New Agents

When you add a new agent to the platform:

### 1. Ensure Backend Endpoint Works

The dashboard calls:
```
GET http://localhost:5000/api/assets/asset-{AGENT_ID}/compliance
```

This endpoint is already configured in [`backend/compliance_endpoints.py`](file:///d:/Downloads/enterprise-omni-agent-ai-platform/backend/compliance_endpoints.py#L523-L539)

### 2. Open Dashboard with New Agent ID

**Option A: Use URL parameter**
```
agent_compliance_dashboard.html?agent=NEW_AGENT_ID
```

**Option B: Use the input box**
- Enter `NEW_AGENT_ID` in the input box
- Click "Load Agent"

### 3. No Files Needed!

Unlike the old approach, **you don't need to create a separate HTML file** for each agent. The same `agent_compliance_dashboard.html` file works for **all agents** in your platform!

---

## Technical Details

### API Integration

The dashboard fetches data from:
```javascript
fetch(`http://localhost:5000/api/assets/asset-${agentId}/compliance`)
```

**Expected Response:**
```json
[
  {
    "assetId": "asset-EILT0197",
    "controlId": "PCI-1.1.1",
    "status": "Compliant",
    "lastUpdated": "2026-01-07T...",
    "evidence": [
      {
        "id": "auto-ev-...",
        "name": "System Check: Windows Firewall Profiles",
        "content": "# System Compliance Evidence\n...",
        "uploadedAt": "2026-01-07T...",
        "systemGenerated": true
      }
    ]
  }
]
```

### File Structure

```
enterprise-omni-agent-ai-platform/
├── agent_compliance_dashboard.html   ← Universal dashboard
├── backend/
│   └── compliance_endpoints.py       ← API endpoints
│       └── /api/assets/{id}/compliance
└── static/
    └── evidence/                      ← Uploaded evidence files
```

---

## Screenshots

### Dashboard Overview
![Dashboard](file:///C:/Users/srihari/.gemini/antigravity/brain/16fa8047-772d-4f38-9fa2-be5488b2412b/dashboard_initial_load_1767730670296.png)

### Expanded Evidence View
![Evidence](file:///C:/Users/srihari/.gemini/antigravity/brain/16fa8047-772d-4f38-9fa2-be5488b2412b/expanded_evidence_view_1767730692024.png)

### Search Filtering
![Search](file:///C:/Users/srihari/.gemini/antigravity/brain/16fa8047-772d-4f38-9fa2-be5488b2412b/filtered_search_results_1767730726714.png)

---

## Customization

### Change Agent ID Programmatically

```javascript
// In browser console
const url = new URL(window.location);
url.searchParams.set('agent', 'YOUR-AGENT-ID');
window.location.href = url.toString();
```

### Embed in Your Application

```html
<iframe 
  src="agent_compliance_dashboard.html?agent=EILT0197" 
  width="100%" 
  height="800px"
  frameborder="0">
</iframe>
```

---

## Troubleshooting

### Error: "HTTP 404: Not Found"

**Cause:** Agent ID doesn't exist in the database  
**Solution:** Verify the agent ID is correct and the agent has reported compliance data

### No Evidence Showing

**Cause:** Agent hasn't collected compliance data yet  
**Solution:** Wait for agent heartbeat or manually trigger compliance scan

### Search Not Working

**Cause:** JavaScript disabled or browser compatibility  
**Solution:** Use a modern browser (Chrome, Edge, Firefox) with JavaScript enabled

---

## Benefits Over Per-Agent Files

| Old Approach | New Universal Dashboard |
|--------------|-------------------------|
| Create HTML file per agent | ✅ One file for all agents |
| Manual updates needed | ✅ Automatic from API |
| No search/filter | ✅ Built-in search & filter |
| Static data | ✅ Real-time data loading |
| No evidence display | ✅ Full evidence viewer |

---

## Example: Testing Multiple Agents

```bash
# Agent 1
start "agent_compliance_dashboard.html?agent=EILT0197"

# Agent 2
start "agent_compliance_dashboard.html?agent=SERVER-001"

# Agent 3
start "agent_compliance_dashboard.html?agent=WORKSTATION-042"
```

Each will load its own compliance data automatically!

---

## Support

For issues or questions:
1. Check the browser console for API errors
2. Verify backend is running: `http://localhost:5000/api/assets/asset-{ID}/compliance`
3. Ensure MongoDB has compliance data for the agent

---

## Summary

✨ **One dashboard to rule them all!**  
🚀 **No setup required for new agents**  
📊 **Full evidence visibility**  
🔍 **Powerful search & filter**  
💅 **Beautiful, modern UI**
