import asyncio
import json
import re
import ast
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

def load_mappings():
    path = os.path.join(os.path.dirname(__file__), "compliance_endpoints.py")
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    
    # We'll use a simple regex or AST. Regex is easier for this specific case if it's formatted predictably
    # Or just ast.parse and find the dictionary
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MAPPINGS":
                    if isinstance(node.value, ast.Dict):
                        mappings = {}
                        for k, v in zip(node.value.keys, node.value.values):
                            if isinstance(k, ast.Constant):
                                key = k.value
                                vals = []
                                if isinstance(v, ast.List):
                                    for elt in v.elts:
                                        if isinstance(elt, ast.Constant):
                                            vals.append(elt.value)
                                mappings[key] = vals
                        return mappings
    return {}

async def analyze_relevance():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.omni_platform

    print("Analyzing Compliance Evidence Relevance...")
    
    # 1. Get all frameworks and their controls
    frameworks = await db.compliance_frameworks.find({}).to_list(length=100)
    all_controls = {}
    for fw in frameworks:
        for ctrl in fw.get("controls", []):
            all_controls[ctrl["id"]] = {
                "name": ctrl.get("name", ""),
                "description": ctrl.get("description", ""),
                "category": ctrl.get("category", ""),
                "framework": fw["id"]
            }

    print(f"Loaded {len(all_controls)} controls from {len(frameworks)} frameworks.")

    # 2. Analyze MAPPINGS
    MAPPINGS = load_mappings()
    print(f"Loaded {len(MAPPINGS)} check mappings.")
    
    mapped_controls = {}
    for check_name, target_controls in MAPPINGS.items():
        for raw_ctrl in target_controls:
            ctrl_id = raw_ctrl
            for prefix in ["nistcsf-", "pci-dss-", "iso27001-", "hipaa-", "gdpr-", "dpdp-", "fedramp-", "ccpa-", "hitrust-", "cmmc-", "csa-", "cobit-", "dora-"]:
                if ctrl_id.startswith(prefix):
                    ctrl_id = ctrl_id[len(prefix):]
                    break
            
            if ctrl_id not in mapped_controls:
                mapped_controls[ctrl_id] = []
            mapped_controls[ctrl_id].append(check_name)

    # 3. Identify potentially irrelevant mappings
    policy_keywords = r"(policy|procedure|training|awareness|governance|process|review|audit plan|management approval|contracts|agreements|roles|responsibilities|charter|risk assessment|business continuity|disaster recovery plan|bcp|drp|incident response plan|physical|screening|personnel)"
    
    flagged_mappings = []
    
    for ctrl_id, checks in mapped_controls.items():
        if ctrl_id not in all_controls:
            continue
            
        ctrl = all_controls[ctrl_id]
        desc = ctrl["description"].lower() + " " + ctrl["name"].lower()
        
        is_policy_control = bool(re.search(policy_keywords, desc))
        
        for check in checks:
            if is_policy_control and "Simulation" in check:
                flagged_mappings.append({
                    "framework": ctrl["framework"],
                    "control_id": ctrl_id,
                    "control_name": ctrl["name"],
                    "check_mapped": check,
                    "reason": "Simulation check mapped to a policy/admin control."
                })
            elif is_policy_control and "Admin Check:" in check:
                flagged_mappings.append({
                    "framework": ctrl["framework"],
                    "control_id": ctrl_id,
                    "control_name": ctrl["name"],
                    "check_mapped": check,
                    "reason": "Raw technical setting mapped to a policy/admin control."
                })

    print(f"\nFound {len(flagged_mappings)} potentially irrelevant evidence mappings.")
    
    framework_flags = {}
    for flag in flagged_mappings:
        fw = flag["framework"]
        if fw not in framework_flags:
            framework_flags[fw] = []
        framework_flags[fw].append(flag)
        
    for fw, flags in framework_flags.items():
        print(f"\n--- Framework: {fw.upper()} ({len(flags)} flagged) ---")
        for i, flag in enumerate(flags[:5]):
            print(f"  Control: {flag['control_id']} - {flag['control_name']}")
            print(f"  Mapped:  {flag['check_mapped']}")
            print(f"  Reason:  {flag['reason']}\n")
        if len(flags) > 5:
            print(f"  ...and {len(flags) - 5} more.")

if __name__ == "__main__":
    asyncio.run(analyze_relevance())
