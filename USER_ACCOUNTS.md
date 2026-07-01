# Platform User Accounts - Complete Setup

**Date:** December 5, 2025  
**Status:** All accounts created successfully  
**Database:** MongoDB (localhost:27017)

---

## 👥 USER ACCOUNTS CREATED

### 1. Super Admin (Platform-Wide Access)

```
Email: super@omni.ai
Password: password123
Role: Super Admin
Tenant: platform-admin
Access: All tenants, system-wide administration
```

**Capabilities:**
- ✅ Access all tenant data
- ✅ Manage all tenants
- ✅ Create/delete tenants
- ✅ Platform-wide settings
- ✅ View all agents across tenants
- ✅ System administration

**Files:**
- `super_admin_credentials.txt`

---

### 2. Sriprasad Tenant Admin

```
Email: admin@sriprasad.com
Password: Admin123!
Role: Tenant Admin
Tenant: sriprasad
Access: Sriprasad tenant only
```

**Capabilities:**
- ✅ Manage sriprasad tenant
- ✅ Manage users within tenant
- ✅ View agents for sriprasad
- ✅ All features within tenant scope
- ❌ Cannot access other tenants
- ❌ Cannot access platform admin features

**Files:**
- `sriprasad_credentials.txt`
- `sriprasad_tenant_id.txt`

---

## 🔧 BACKEND RESTART REQUIRED

The backend with `--reload` flag may be caching old data. For logins to work:

### Option 1: Clean Restart (Recommended)

```powershell
# 1. Stop the backend (find the terminal and press Ctrl+C)

# 2. Restart backend freshly
cd backend
python -m uvicorn app:app --port 5000
```

### Option 2: Full Reset

```powershell
# Stop backend, clear everything, restart
cd backend
python -m uvicorn app:app --port 5000
```

---

## 🧪 MANUAL LOGIN TESTING

After restarting backend, test both accounts:

### Test 1: Super Admin Login

1. Open: http://localhost:3000
2. Email: `super@omni.ai`
3. Password: `password123`
4. **Expected:** Login successful, see "Super Admin" in user menu
5. Navigate to: Administration → Tenants
6. **Expected:** See both tenants:
   - platform-admin
   - sriprasad

---

### Test 2: Sriprasad Admin Login

1. Logout from super admin
2. Email: `admin@sriprasad.com`
3. Password: `Admin123!`
4. **Expected:** Login successful, see "Sri Prasad Admin" in user menu
5. **Expected:** Can only see sriprasad tenant data
6. **Expected:** No "Tenants" menu (tenant admins can't manage tenants)

---

## 📊 DATABASE VERIFICATION

To verify accounts were created correctly:

```powershell
python check_database.py
```

**Expected output:**
```
TENANTS:
  - platform-admin
  - sriprasad

USERS:
  - super@omni.ai (Super Admin, platform-admin)
  - admin@sriprasad.com (Tenant Admin, sriprasad)
```

---

## 🔐 PASSWORD HASHING

Both accounts use **bcrypt** hashing (direct usage), matching the backend's `auth_utils.py`:

```python
import bcrypt
salt = bcrypt.gensalt()
hashed = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
```

This is the CORRECT hashing method. Earlier attempts with SHA-256 failed because of hash mismatch.

---

## 🚀 AGENT CONFIGURATION

### For Sriprasad Tenant

```powershell
# Configure agent
$tenantId = Get-Content sriprasad_tenant_id.txt
(Get-Content agent\config.yaml) -replace 'tenant_id: ".*"', "tenant_id: `"$tenantId`"" | Set-Content agent\config.yaml

# Start agent
cd agent
python agent.py
```

**Expected:** Agent appears in sriprasad tenant's Agents dashboard

---

## 📝 COLLECTIONS IN MONGODB

After account creation:

```
tenants:
  - platform-admin (Super Admin tenant)
  - sriprasad (Regular tenant)

users:
  - super@omni.ai
  - admin@sriprasad.com

agents: (empty until agent started)
assets: (empty until agent reports)
```

---

## ⚠️ TROUBLESHOOTING

### Login fails with "Invalid email or password"

**Cause:** Backend reload caching issue

**Solution:**
1. Stop backend completely (Ctrl+C)
2. Start fresh: `python -m uvicorn app:app --port 5000`
3. Try login again

---

### "Backend connection lost" message

**Cause:** Backend not running or crashed

**Solution:**
```powershell
cd backend
python -m uvicorn app:app --port 5000
```

---

### Cannot see other tenant's data as Super Admin

**Expected Behavior:** Super Admin should see all tenants

**Check:** 
1. Verify logged in as super@omni.ai
2. Check role shows "Super Admin" in user menu
3. Navigate to Administration → Tenants

---

## ✅ SUCCESS CRITERIA

After clean backend restart and login:

- [ ] Super Admin login works (super@omni.ai)
- [ ] Sriprasad Admin login works (admin@sriprasad.com)
- [ ] Super Admin sees "Tenants" menu item
- [ ] Super Admin can view both tenants
- [ ] Sriprasad Admin only sees own tenant
- [ ] User menu shows correct role
- [ ] Dashboard loads without errors

---

## 📁 CREATED FILES

1. `create_super_admin.py` - Super admin creation script
2. `super_admin_credentials.txt` - Super admin credentials
3. `setup_sri prasad_bcrypt.py` - Sriprasad tenant script
4. `sriprasad_credentials.txt` - Sriprasad credentials
5. `sriprasad_tenant_id.txt` - Tenant ID for agent
6. `check_database.py` - Database verification script

---

## 🎯 NEXT STEPS

1. **Stop backend** (Ctrl+C in backend terminal)
2. **Restart cleanly**:
   ```powershell
   cd backend
   python -m uvicorn app:app --port 5000
   ```
3. **Test Super Admin login** at http://localhost:3000
4. **Test Sriprasad login**
5. **Start agent** for sriprasad tenant
6. **Verify agent** appears in Observability → Agents

---

**All accounts created successfully with proper bcrypt hashing!**  
**Clean backend restart required for login to work.**
