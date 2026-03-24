"""
Update framework control statuses based on evidence collected in asset_compliance.
Maps all controls that have evidence to 'Implemented' in the compliance_frameworks collection.
"""
from pymongo import MongoClient

db = MongoClient('mongodb://localhost:27017')['omni_platform']

# Get all controlIds that have evidence in asset_compliance
evidence_controls = set()
for rec in db.asset_compliance.find({}, {'controlId': 1, 'status': 1}):
    ctrl = rec.get('controlId')
    status = rec.get('status', 'Compliant')
    if ctrl:
        evidence_controls.add((ctrl, status))

print(f"Found {len(evidence_controls)} control IDs with evidence.")

# Map compliance status to framework status
def map_status(status):
    if status in ('Compliant', 'Pass'):
        return 'Implemented'
    elif status in ('Warning', 'In Progress'):
        return 'In Progress'
    elif status in ('Non-Compliant', 'Fail', 'At Risk'):
        return 'At Risk'
    return 'Implemented'

# Build a dict of ctrl_id -> best_status
ctrl_status_map = {}
for ctrl, status in evidence_controls:
    mapped = map_status(status)
    # Priority: Implemented > In Progress > At Risk
    current = ctrl_status_map.get(ctrl, 'Not Implemented')
    priority = {'Implemented': 3, 'In Progress': 2, 'At Risk': 1, 'Not Implemented': 0}
    if priority.get(mapped, 0) > priority.get(current, 0):
        ctrl_status_map[ctrl] = mapped

print(f"\nControl status map (sample):")
for k, v in list(ctrl_status_map.items())[:10]:
    print(f"  {k} -> {v}")

# Update all frameworks
frameworks = list(db.compliance_frameworks.find({}, {'id': 1, 'controls': 1}))
print(f"\nFound {len(frameworks)} frameworks to update.")

total_updated = 0
for fw in frameworks:
    fw_id = fw.get('id', 'unknown')
    controls = fw.get('controls', [])
    
    updates_needed = []
    for i, ctrl in enumerate(controls):
        ctrl_id = ctrl.get('id')
        if ctrl_id and ctrl_id in ctrl_status_map:
            new_status = ctrl_status_map[ctrl_id]
            old_status = ctrl.get('status', 'Not Implemented')
            if old_status != new_status:
                updates_needed.append((i, ctrl_id, new_status, old_status))
    
    if updates_needed:
        for i, ctrl_id, new_status, old_status in updates_needed:
            import datetime
            db.compliance_frameworks.update_one(
                {'id': fw_id, 'controls.id': ctrl_id},
                {'$set': {
                    'controls.$.status': new_status,
                    'controls.$.lastReviewed': datetime.datetime.utcnow().strftime('%Y-%m-%d'),
                }}
            )
            total_updated += 1
        print(f"  [{fw_id}] Updated {len(updates_needed)} controls")

print(f"\n✅ Total controls updated across all frameworks: {total_updated}")

# Recalculate progress for each framework
for fw in db.compliance_frameworks.find({}, {'id': 1, 'controls': 1}):
    controls = fw.get('controls', [])
    total = len(controls)
    if total == 0:
        continue
    implemented = sum(1 for c in controls if c.get('status') == 'Implemented')
    in_progress = sum(1 for c in controls if c.get('status') == 'In Progress')
    progress = round(((implemented + in_progress * 0.5) / total) * 100)
    
    # Determine overall framework status
    if implemented == total:
        fw_status = 'Compliant'
    elif implemented > 0 or in_progress > 0:
        fw_status = 'In Progress'
    else:
        fw_status = 'Not Started'
    
    db.compliance_frameworks.update_one(
        {'id': fw['id']},
        {'$set': {'progress': progress, 'status': fw_status}}
    )
    print(f"  [{fw['id']}] {implemented}/{total} implemented | progress: {progress}% | status: {fw_status}")

print("\n🏁 Framework progress recalculated.")
