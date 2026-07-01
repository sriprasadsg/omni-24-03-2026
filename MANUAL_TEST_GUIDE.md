# Multi-Network Scanning - Browser Testing Guide

## Prerequisites
✅ Backend server running on port 5000
✅ Frontend running on port 3000
✅ MongoDB running on port 27017

---

## Test Procedure

### Part 1: UI Element Verification

1. **Open the application**
   - Navigate to: `http://localhost:3000/network-observability`
   - Login credentials:
     - Email: `super@omni.ai`
     - Password: `superadmin`

2. **Verify new UI element**
   - Look for **"Scan All Networks"** checkbox in the toolbar
   - Location: Between "Refresh List" button and "Scan Network" button
   - Expected state: **CHECKED** by default ✓
   - Screenshot: `test-1-checkbox-visible.png`

---

### Part 2: Full Network Scan Test

3. **Trigger full network scan**
   - Ensure "Scan All Networks" is **CHECKED** ✓
   - Click **"Scan Network"** button
   - Button should show "Scanning..." temporarily
   - Wait 10-15 seconds for scan to complete

4. **Verify device list**
   - List should populate with discovered devices
   - Check "Total Devices" stat card for count
   - Note the number: `___ devices found`
   - Screenshot: `test-2-full-scan-results.png`

5. **Check device details**
   - Look at device list entries
   - Each device should show:
     - Hostname or IP address
     - Status (Up/Down)
     - Device Type (if detected)
   - Note if multiple subnets are visible in device info

---

### Part 3: Topology Visualization Test

6. **Switch to Map view**
   - Click the **"Map"** toggle button (top toolbar)
   - Wait for topology image to generate (5-10 seconds)

7. **Verify multi-subnet visualization**
   - Image should load successfully (not broken image icon)
   - Look for:
     - Server node in center (blue)
     - Device nodes around it (colored by type)
     - **If multiple subnets detected:**
       - Devices grouped in colored wedge sectors
       - Subnet labels (e.g., "Subnet: 192.168.1.0/24")
       - Different background colors for each subnet sector
     - **If single subnet:**
       - Simple circular star layout
   - Screenshot: `test-3-topology-map.png`

8. **Check map quality**
   - Zoom in if needed to read labels
   - Verify title shows: "Network Topology - Discovered Devices (X across Y subnet(s))"
   - Note subnet count from title: `___ subnet(s)`

---

### Part 4: Single Subnet Scan Test

9. **Switch back to List view**
   - Click **"List"** toggle button

10. **Configure single subnet scan**
    - **UNCHECK** the "Scan All Networks" checkbox ☐
    - Screenshot: `test-4-checkbox-unchecked.png`

11. **Trigger single subnet scan**
    - Click **"Scan Network"** button
    - Wait 10-15 seconds

12. **Compare results**
    - Check "Total Devices" count again
    - Compare with full scan count from step 4
    - Expected:
      - If you have multiple subnets: `Single scan devices < Full scan devices`
      - If single subnet environment: `Same count as before`
    - Note the count: `___ devices found (single subnet)`
    - Screenshot: `test-5-single-scan-results.png`

---

### Part 5: Map Refresh Test

13. **Test map refresh**
    - Switch to "Map" view again
    - Click **"Refresh Map Image"** button
    - Map should reload (may take 5-10 seconds)
    - Screenshot: `test-6-map-refreshed.png`

---

## Expected Results Summary

| Test | Expected Behavior | ✓/✗ | Notes |
|------|-------------------|-----|-------|
| Checkbox visible | "Scan All Networks" checkbox present | | |
| Default state | Checkbox checked by default | | |
| Full scan | Scans all detected subnets | | Devices: ___ |
| Device list | Shows discovered devices | | |
| Topology map | Generates and displays correctly | | Subnets: ___ |
| Multi-subnet viz | Colored sectors if multiple subnets | | |
| Single scan | Scans only primary subnet | | Devices: ___ |
| Toggle works | Checkbox affects scan behavior | | |
| Map refresh | Regenerates topology on demand | | |

---

## Troubleshooting

### Checkbox not visible
- **Check:** Frontend code updated correctly
- **Fix:** Clear browser cache and refresh
- **Verify:** Check browser console for errors

### Scan fails
- **Check:** Backend server running and accessible
- **Fix:** Restart backend: `python -m uvicorn app:app --port 5000`
- **Verify:** Navigate to http://localhost:5000/health

### Map shows broken image
- **Check:** Topology image generation
- **Fix:** Check backend console for visualization errors
- **Verify:** Try "Refresh Map Image" button

### Same device count for both scans
- **Normal if:** Your system has only one active network interface
- **Check:** Run in backend/: `python -c "from server_discovery import ServerDiscovery; print(ServerDiscovery._get_all_local_subnets())"`
- **Expected:** If output shows only 1 subnet, same count is correct

---

## Test Data Collection

Please note the following for reporting:

1. **Total subnets detected:** ___
2. **Subnets list:** ___
3. **Full scan device count:** ___
4. **Single scan device count:** ___
5. **Topology visualization:** Worked / Had issues
6. **Any errors encountered:** ___

---

## Screenshots Checklist

- [ ] `test-1-checkbox-visible.png` - Checkbox in toolbar
- [ ] `test-2-full-scan-results.png` - Device list after full scan
- [ ] `test-3-topology-map.png` - Multi-subnet topology visualization
- [ ] `test-4-checkbox-unchecked.png` - Unchecked checkbox
- [ ] `test-5-single-scan-results.png` - Device list after single scan
- [ ] `test-6-map-refreshed.png` - Refreshed map

---

## Success Criteria

✅ All tests should pass with:
- Checkbox visible and functional
- Both scan modes working
- Topology map generating correctly
- UI responsive and error-free

---

**Testing Time:** Approximately 5-10 minutes
**Difficulty:** Easy - No technical knowledge required
