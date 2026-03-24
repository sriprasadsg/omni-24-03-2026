# Running the Project with Exafluence Tenant

## ✅ What's Been Implemented

**Backend Validation Added:**
- Agents **MUST** have a `tenant_id` configured
- Agents without `tenant_id` are **REJECTED** with a clear error message
- Invalid `tenant_id` values are also **REJECTED**

---

## 📋 Prerequisites

You MUST have MongoDB running on `localhost:27017`.

### Start MongoDB:

**Option 1: Docker (Easiest)**
```powershell
docker run -d -p 27017:27017 --name omni-mongodb mongo:latest
```

**Option 2: Windows Service**
```powershell
# If MongoDB is installed as a service
net start MongoDB
```

---

## 🚀 Step-by-Step Execution

### Terminal 1: Start Backend

```powershell
cd d:\Downloads\enterprise-omni-agent-ai-platform\backend
.\venv\Scripts\activate
python -m uvicorn app:app --reload --port 5000
```

**Wait for:** `Application startup complete`

---

### Terminal 2: Start Frontend

```powershell
cd d:\Downloads\enterprise-omni-agent-ai-platform
npm run dev
```

**Wait for:** `Local: http://localhost:3000/`

---

### Terminal 3: Create Exafluence Tenant

```powershell
cd d:\Downloads\enterprise-omni-agent-ai-platform
python create_exafluence_tenant.py
```

**This will:**
- Create "Exafluence" company
- Create admin user: `admin@exafluence.com`
- Password: `ExafluenceSecure123!`
- Save tenant ID to `exafluence_tenant_id.txt`

**Expected Output:**
```
✅ Exafluence tenant created successfully!

Tenant ID: tenant_xxxxxxxxxxxx
Tenant Name: Exafluence
...
```

---

### Terminal 3 (continued): Configure Agent

```powershell
# Read the tenant ID from the file
type exafluence_tenant_id.txt
```

**Copy the tenant ID**, then edit `agent/config.yaml`:

```yaml
api_base_url: "http://localhost:5000"
tenant_id: "paste-tenant-id-here"  # ← Paste the actual tenant ID
agent_token: ""
interval_seconds: 30
```

**OR use this command to auto-update (PowerShell):**
```powershell
$tenantId = Get-Content exafluence_tenant_id.txt
(Get-Content agent\config.yaml) -replace 'tenant_id: ".*"', "tenant_id: `"$tenantId`"" | Set-Content agent\config.yaml
Write-Host "✅ Agent configured with tenant: $tenantId"
```

---

### Terminal 4: Run Agent

```powershell
cd d:\Downloads\enterprise-omni-agent-ai-platform\agent
python agent.py
```

**Expected Output:**
```
2025-12-05 14:45:00 - __main__ - INFO - Starting Omni Agent v2.0
...
2025-12-05 14:45:30 - __main__ - INFO - Heartbeat -> 200
```

**✅ If you see `Heartbeat -> 200`, the agent is successfully registered!**

**❌ If you see `Heartbeat -> 400` or `Heartbeat -> 404`:**
- Error 400: No `tenant_id` configured
- Error 404: Invalid `tenant_id` (doesn't exist)

---

## 🔍 Verify Agent Registration

1. **Open Browser:** http://localhost:3000
2. **Login:**
   - Email: `admin@exafluence.com`
   - Password: `ExafluenceSecure123!`
3. **Navigate to:** Observability → Agents
4. **You should see:** Your local machine registered as an agent under Exafluence

---

## 🧪 Testing Rejection (Optional)

To verify agents without tenant_id are rejected:

1. **Edit `agent/config.yaml`** and remove or empty the tenant_id:
   ```yaml
   tenant_id: ""
   ```

2. **Run agent** and you'll see:
   ```
   ERROR - Heartbeat error: ...
   ```

3. **Check agent logs** - Backend will respond with:
   ```json
   {
     "status": "rejected",
     "error": "Agent registration requires a valid tenant_id..."
   }
   ```

4. **Restore the correct tenant_id** to fix it.

---

## 📊 Current Status

### ✅ Implemented:
- Backend validation for tenant_id (REQUIRED)
- Rejection of agents without tenant_id
- Rejection of agents with invalid tenant_id
- Exafluence tenant creation script
- Auto-configuration helper commands

### 🎯 Expected Behavior:
1. Agent with **valid Exafluence tenant_id** → ✅ Registered successfully
2. Agent with **no tenant_id** → ❌ Rejected (HTTP 400)
3. Agent with **invalid tenant_id** → ❌ Rejected (HTTP 404)
4. Agent with **different tenant's ID** → ✅ Registered under that tenant

---

## 🔑 Login Credentials

### Exafluence Account
- **Email:** admin@exafluence.com
- **Password:** ExafluenceSecure123!

### Super Admin (Platform-wide)
- **Email:** super@omni.ai  
- **Password:** password123

---

## 📝 Notes

- **Multi-Tenant Isolation:** Agents are isolated by `tenant_id`
- **Security:** Each tenant can only see their own agents
- **Validation:** Strict tenant validation prevents unauthorized agent registration
- **MongoDB Required:** The platform uses MongoDB for data persistence

---

## 🆘 Troubleshooting

### "Cannot connect to backend"
→ Start backend server (Terminal 1)

### "MongoDB connection failed"
→ Start MongoDB (see Prerequisites)

### "Tenant already exists"
→ Tenant created previously, just configure agent with existing tenant_id

### "Agent not appearing in dashboard"
→ 1. Verify tenant_id matches logged-in user's tenant
→ 2. Check agent logs for `Heartbeat -> 200`
→ 3. Refresh browser page

---

**All systems configured! Follow the terminal commands above to run the complete platform with Exafluence tenant isolation. 🚀**
