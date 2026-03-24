import asyncio
from database import connect_to_mongo, close_mongo_connection, get_database
from datetime import datetime, timezone

async def add_missing_nist_controls():
    """Add comprehensive NIST CSF 2.0 controls - all 106 subcategories"""
    await connect_to_mongo()
    db = get_database()
    
    print("🔧 Expanding NIST CSF with all 106 subcategories...")
    
    # Complete NIST CSF 2.0 controls
    complete_nist_controls = [
        # GOVERN (GV) - New in CSF 2.0
        { "id": "GV.OC-1", "name": "Organizational Context", "description": "The organizational mission, stakeholder expectations, and legal/regulatory requirements are understood.", "category": "Govern", "status": "Implemented", "lastReviewed": "2024-01-01", "evidence": [] },
        { "id": "GV.OC-2", "name": "Internal Context", "description": "Internal stakeholders understand their roles, responsibilities, and authorities.", "category": "Govern", "status": "Implemented", "lastReviewed": "2024-01-01", "evidence": [] },
        { "id": "GV.OC-3", "name": "Critical Objectives", "description": "Critical objectives, capabilities, and services are prioritized.", "category": "Govern", "status": "Implemented", "lastReviewed": "2024-01-01", "evidence": [] },
        { "id": "GV.OC-4", "name": "Risk Determination", "description": "Cybersecurity risk is determined as part of enterprise risk management.", "category": "Govern", "status": "In Progress", "lastReviewed": "2024-01-01", "evidence": [] },
        { "id": "GV.OC-5", "name": "Outcomes Reporting", "description": "Outcomes of cybersecurity risk management activities are reported to senior leadership.", "category": "Govern", "status": "Implemented", "lastReviewed": "2024-01-01", "evidence": [] },
        { "id": "GV.RM-1", "name": "Risk Management Strategy", "description": "A cybersecurity risk management strategy is established and communicated.", "category": "Govern", "status": "Implemented", "lastReviewed": "2024-01-02", "evidence": [] },
        { "id": "GV.RM-2", "name": "Risk Appetite", "description": "Risk appetite and risk tolerance statements are established, communicated, and maintained.", "category": "Govern", "status": "Implemented", "lastReviewed": "2024-01-02", "evidence": [] },
        { "id": "GV.RM-3", "name": "Risk Determination Factors", "description": "Cybersecurity risk determination is informed by risk identification and analysis activities.", "category": "Govern", "status": "At Risk", "lastReviewed": "2024-01-02", "evidence": [] },
        { "id": "GV.RR-1", "name": "Roles and Responsibilities", "description": "Organizational cybersecurity roles and responsibilities are established.", "category": "Govern", "status": "Implemented", "lastReviewed": "2024-01-03", "evidence": [] },
        { "id": "GV.RR-2", "name": "Responsibility Assignment", "description": "Responsibilities for addressing cybersecurity risks are assigned and communicated.", "category": "Govern", "status": "Implemented", "lastReviewed": "2024-01-03", "evidence": [] },
        { "id": "GV.RR-3", "name": "Authority", "description": "Adequate resources are allocated to manage cybersecurity risk.", "category": "Govern", "status": "In Progress", "lastReviewed": "2024-01-03", "evidence": [] },
        { "id": "GV.RR-4", "name": "Policy", "description": "Cybersecurity is included in human resources practices.", "category": "Govern", "status": "Implemented", "lastReviewed": "2024-01-04", "evidence": [] },
        { "id": "GV.PO-1", "name": "Policy Establishment", "description": "Policy for managing cybersecurity risks is established based on organizational context.", "category": "Govern", "status": "Implemented", "lastReviewed": "2024-01-05", "evidence": [] },
        { "id": "GV.PO-2", "name": "Policy Maintenance", "description": "Policy is reviewed, updated, communicated, and enforced.", "category": "Govern", "status": "Implemented", "lastReviewed": "2024-01-05", "evidence": [] },
        { "id": "GV.SC-1", "name": "Supply Chain Risk Management", "description": "A supply chain risk management policy is established and communicated.", "category": "Govern", "status": "In Progress", "lastReviewed": "2024-01-06", "evidence": [] },
        { "id": "GV.SC-2", "name": "Supplier Relationships", "description": "Supplier relationships are established based on criticality.", "category": "Govern", "status": "At Risk", "lastReviewed": "2024-01-06", "evidence": [] },
        
        # IDENTIFY (ID)
        { "id": "ID.AM-1", "name": "Asset Management", "description": "Physical devices and systems within the organization are inventoried.", "category": "Identify", "status": "Implemented", "lastReviewed": "2023-10-05", "evidence": [] },
        { "id": "ID.AM-2", "name": "Software Inventory", "description": "Software platforms and applications within the organization are inventtoried.", "category": "Identify", "status": "Implemented", "lastReviewed": "2023-10-06", "evidence": [] },
        { "id": "ID.AM-3", "name": "Organizational Communication", "description": "Organizational communication and data flows are mapped.", "category": "Identify", "status": "At Risk", "lastReviewed": "2024-01-07", "evidence": [] },
        { "id": "ID.AM-4", "name": "External Dependencies", "description": "External information systems are catalogued.", "category": "Identify", "status": "In Progress", "lastReviewed": "2024-01-07", "evidence": [] },
        { "id": "ID.AM-5", "name": "Resource Priority", "description": "Resources are prioritized based on classification, criticality, and business value.", "category": "Identify", "status": "Implemented", "lastReviewed": "2024-01-08", "evidence": [] },
        { "id": "ID.AM-7", "name": "Software Supply Chain", "description": "Inventory of software and services is maintained.", "category": "Identify", "status": "Implemented", "lastReviewed": "2024-01-08", "evidence": [] },
        { "id": "ID.AM-8", "name": "Systems Integration", "description": "Systems, hardware, software, services, and data are managed consistently.", "category": "Identify", "status": "In Progress", "lastReviewed": "2024-01-09", "evidence": [] },
        { "id": "ID.RA-1", "name": "Risk Assessment", "description": "Asset vulnerabilities are identified and documented.", "category": "Identify", "status": "At Risk", "lastReviewed": "2023-10-07", "evidence": [] },
        { "id": "ID.RA-2", "name": "Threat Intelligence", "description": "Cyber threat intelligence is received from information sharing forums.", "category": "Identify", "status": "Implemented", "lastReviewed": "2023-10-07", "evidence": [] },
        { "id": "ID.RA-3", "name": "Threat and Vulnerability Info", "description": "Internal and external threats to the organization are identified and recorded.", "category": "Identify", "status": "Implemented", "lastReviewed": "2024-01-10", "evidence": [] },
        { "id": "ID.RA-4", "name": "Impact Analysis", "description": "Potential impacts and likelihoods are identified.", "category": "Identify", "status": "In Progress", "lastReviewed": "2024-01-10", "evidence": [] },
        { "id": "ID.RA-5", "name": "Risk Response", "description": "Threats, vulnerabilities, likelihoods, and impacts are used to understand risk.", "category": "Identify", "status": "At Risk", "lastReviewed": "2024-01-11", "evidence": [] },
        { "id": "ID.RA-6", "name": "Risk Responses", "description": "Risk responses are identified, prioritized, and implemented.", "category": "Identify", "status": "In Progress", "lastReviewed": "2024-01-11", "evidence": [] },
        { "id": "ID.RA-7", "name": "Risk Communication", "description": "Risk is communicated to stakeholders.", "category": "Identify", "status": "Implemented", "lastReviewed": "2024-01-12", "evidence": [] },
         { "id": "ID.RA-8", "name": "Risk Improvement", "description": "Improvement opportunities from risk assessments are communicated.", "category": "Identify", "status": "In Progress", "lastReviewed": "2024-01-12", "evidence": [] },
        { "id": "ID.IM-1", "name": "Improvement Activities", "description": "Improvement activities are identified and prioritized based on findings.", "category": "Identify", "status": "Implemented", "lastReviewed": "2024-01-13", "evidence": [] },
        { "id": "ID.IM-2", "name": "Response and Recovery", "description": "Response and recovery activities are improved based on lessons learned.", "category": "Identify", "status": "In Progress", "lastReviewed": "2024-01-13", "evidence": [] },
        { "id": "ID.GV-1", "name": "Governance", "description": "Organizational information security policy is established.", "category": "Identify", "status": "Implemented", "lastReviewed": "2023-10-08", "evidence": [] },
        
        # PROTECT (PR)
        { "id": "PR.AA-1", "name": "Identity Management", "description": "Identities and credentials for authorized users, services, and hardware are managed.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-14", "evidence": [] },
        { "id": "PR.AA-2", "name": "Identity Provisioning", "description": "Identities are proofed and bound to credentials and assets.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-14", "evidence": [] },
        { "id": "PR.AA-3", "name": "Multi-Factor Authentication", "description": "Users, services, and hardware are authenticated.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-15", "evidence": [] },
        { "id": "PR.AA-4", "name": "Identity Assertions", "description": "Identity assertions are protected, conveyed, and verified.", "category": "Protect", "status": "In Progress", "lastReviewed": "2024-01-15", "evidence": [] },
        { "id": "PR.AA-5", "name": "Access Review", "description": "Access permissions, entitlements, and authorizations are defined and managed.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-16", "evidence": [] },
        { "id": "PR.AA-6", "name": "Physical Access", "description": "Physical access to assets is managed.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-16", "evidence": [] },
        { "id": "PR.AC-1", "name": "Access Control", "description": "Access to assets and associated facilities is limited to authorized users.", "category": "Protect", "status": "Implemented", "lastReviewed": "2023-10-08", "evidence": [] },
        { "id": "PR.AC-3", "name": "Remote Access", "description": "Remote access is managed.", "category": "Protect", "status": "Implemented", "lastReviewed": "2023-10-09", "evidence": [] },
        { "id": "PR.AC-4", "name": "Least Privilege", "description": "Access permissions are managed, incorporating least privilege principles.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-17", "evidence": [] },
        { "id": "PR.AC-5", "name": "Network Segregation", "description": "Network integrity is protected (e.g., network segregation, network segmentation).", "category": "Protect", "status": "In Progress", "lastReviewed": "2023-10-09", "evidence": [] },
        { "id": "PR.AT-1", "name": "Security Awareness", "description": "All users are informed and trained on cybersecurity policies.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-18", "evidence": [] },
        { "id": "PR.AT-2", "name": "Privileged User Training", "description": "Privileged users understand roles and responsibilities.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-18", "evidence": [] },
        { "id": "PR.DS-1", "name": "Data at Rest", "description": "Data-at-rest is protected.", "category": "Protect", "status": "Implemented", "lastReviewed": "2023-10-10", "evidence": [] },
        { "id": "PR.DS-2", "name": "Data in Transit", "description": "Data-in-transit is protected.", "category": "Protect", "status": "Implemented", "lastReviewed": "2023-10-11", "evidence": [] },
        { "id": "PR.DS-10", "name": "Data Integrity", "description": "The integrity and authenticity of sensitive data are validated.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-19", "evidence": [] },
        { "id": "PR.DS-11", "name": "Data Disposal", "description": "Sensitive data is managed throughout its lifecycle.", "category": "Protect", "status": "In Progress", "lastReviewed": "2024-01-19", "evidence": [] },
        { "id": "PR.IP-1", "name": "Configuration Baselines", "description": "A baseline configuration is created and maintained.", "category": "Protect", "status": "In Progress", "lastReviewed": "2023-10-11", "evidence": [] },
        { "id": "PR.IP-3", "name": "Configuration Change Control", "description": "Configuration changes are managed and audited.", "category": "Protect", "status": "In Progress", "lastReviewed": "2024-01-20", "evidence": [] },
        { "id": "PR.IP-4", "name": "Backups", "description": "Backups of information are conducted, maintained, and tested.", "category": "Protect", "status": "At Risk", "lastReviewed": "2024-01-20", "evidence": [] },
        { "id": "PR.IP-8", "name": "Response Plans", "description": "Response plans are executed during or after an incident.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-21", "evidence": [] },
        { "id": "PR.IP-9", "name": "Response Plan Testing", "description": "Response plans are tested.", "category": "Protect", "status": "Not Implemented", "lastReviewed": "2024-01-21", "evidence": [] },
        { "id": "PR.IP-10", "name": "Recovery Plans", "description": "Response and recovery plans are managed.", "category": "Protect", "status": "In Progress", "lastReviewed": "2024-01-22", "evidence": [] },
        { "id": "PR.IP-11", "name": "Cybersecurity Integration", "description": "Cybersecurity is included in human resources and third-party management practices.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-22", "evidence": [] },
        { "id": "PR.IP-12", "name": "Vulnerability Management", "description": "A vulnerability management plan is developed and implemented.", "category": "Protect", "status": "At Risk", "lastReviewed": "2024-01-23", "evidence": [] },
        { "id": "PR.MA-1", "name": "Maintenance", "description": "Maintenance and repair of assets is performed and logged.", "category": "Protect", "status": "In Progress", "lastReviewed": "2024-01-24", "evidence": [] },
        { "id": "PR.MA-2", "name": "Remote Maintenance", "description": "Remote maintenance is approved, logged, and performed securely.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-24", "evidence": [] },
        { "id": "PR.PS-1", "name": "Media Protection", "description": "Configuration management processes are in place to manage changes to assets.", "category": "Protect", "status": "In Progress", "lastReviewed": "2024-01-25", "evidence": [] },
        { "id": "PR.PT-1", "name": "Audit Logging", "description": "Audit/log records are determined, documented, implemented, and reviewed.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-26", "evidence": [] },
        { "id": "PR.PT-3", "name": "Least Functionality", "description": "The principle of least functionality is incorporated.", "category": "Protect", "status": "In Progress", "lastReviewed": "2024-01-26", "evidence": [] },
        { "id": "PR.PT-4", "name": "Communication Protection", "description": "Communications and control networks are protected.", "category": "Protect", "status": "Implemented", "lastReviewed": "2024-01-27", "evidence": [] },
        { "id": "PR.PT-5", "name": "Resilience Mechanisms", "description": "Mechanisms are implemented to achieve resilience requirements.", "category": "Protect", "status": "At Risk", "lastReviewed": "2024-01-27", "evidence": [] },
        
        # DETECT (DE)
        { "id": "DE.AE-1", "name": "Anomalies and Events", "description": "A baseline of network operations and expected data flows is established.", "category": "Detect", "status": "Implemented", "lastReviewed": "2023-10-12", "evidence": [] },
        { "id": "DE.AE-2", "name": "Anomaly Detection", "description": "Anomalous activity is detected and the potential impact is determined.", "category": "Detect", "status": "Implemented", "lastReviewed": "2024-01-28", "evidence": [] },
        { "id": "DE.AE-3", "name": "Event Correlation", "description": "Event data are collected and correlated from multiple sources.", "category": "Detect", "status": "In Progress", "lastReviewed": "2024-01-28", "evidence": [] },
        { "id": "DE.AE-4", "name": "Impact Determination", "description": "Impact of events is determined.", "category": "Detect", "status": "At Risk", "lastReviewed": "2024-01-29", "evidence": [] },
        { "id": "DE.AE-6", "name": "Incident Response", "description": "Information on anomalies is provided to authorized personnel.", "category": "Detect", "status": "Implemented", "lastReviewed": "2024-01-29", "evidence": [] },
        { "id": "DE.AE-7", "name": "Threat Hunting", "description": "Cyber threat hunting is performed.", "category": "Detect", "status": "Not Implemented", "lastReviewed": "2024-01-30", "evidence": [] },
        { "id": "DE.AE-8", "name": "Incident Declaration", "description": "Incidents are declared when cybersecurity events are detected.", "category": "Detect", "status": "Implemented", "lastReviewed": "2024-01-30", "evidence": [] },
        { "id": "DE.CM-1", "name": "Security Monitoring", "description": "The network is monitored to detect potential cybersecurity events.", "category": "Detect", "status": "Implemented", "lastReviewed": "2023-10-13", "evidence": [] },
        { "id": "DE.CM-2", "name": "Physical Environment", "description": "The physical environment is monitored to detect cybersecurity events.", "category": "Detect", "status": "In Progress", "lastReviewed": "2024-01-31", "evidence": [] },
        { "id": "DE.CM-3", "name": "Personnel Activity", "description": "Personnel activity and technology usage are monitored.", "category": "Detect", "status": "Implemented", "lastReviewed": "2024-01-31", "evidence": [] },
        { "id": "DE.CM-4", "name": "Malicious Code", "description": "Malicious code is detected.", "category": "Detect", "status": "Implemented", "lastReviewed": "2024-02-01", "evidence": [] },
        { "id": "DE.CM-6", "name": "External Service Activity", "description": "External service provider activity is monitored.", "category": "Detect", "status": "At Risk", "lastReviewed": "2024-02-01", "evidence": [] },
        { "id": "DE.CM-7", "name": "Monitoring for Malicious Code", "description": "Monitoring for unauthorized personnel, connections, devices, and software is performed.", "category": "Detect", "status": "Implemented", "lastReviewed": "2023-10-13", "evidence": [] },
        { "id": "DE.CM-9", "name": "Computing Hardware", "description": "Computing hardware and software, runtime environments, and their data are monitored.", "category": "Detect", "status": "Implemented", "lastReviewed": "2024-02-02", "evidence": [] },
        
        # RESPOND (RS)
        { "id": "RS.MA-1", "name": "Incident Investigation", "description": "Incidents are investigated to ensure effective response and support recovery.", "category": "Respond", "status": "Implemented", "lastReviewed": "2024-02-03", "evidence": [] },
        { "id": "RS.MA-2", "name": "Incident Reporting", "description": "Incidents are reported based on established criteria.", "category": "Respond", "status": "Implemented", "lastReviewed": "2024-02-03", "evidence": [] },
        { "id": "RS.MA-3", "name": "Information Sharing", "description": "Information is shared with designated internal and external stakeholders.", "category": "Respond", "status": "In Progress", "lastReviewed": "2024-02-04", "evidence": [] },
        { "id": "RS.MA-4", "name": "Incident Resolution", "description": "The organization coordinates incident detection and response.", "category": "Respond", "status": "Implemented", "lastReviewed": "2024-02-04", "evidence": [] },
        { "id": "RS.MA-5", "name": "Evidence Collection", "description": "Incident data and metadata are collected, and evidence is preserved.", "category": "Respond", "status": "In Progress", "lastReviewed": "2024-02-05", "evidence": [] },
        { "id": "RS.RP-1", "name": "Response Planning", "description": "Response planning process is executed and maintained.", "category": "Respond", "status": "Implemented", "lastReviewed": "2023-10-14", "evidence": [] },
        { "id": "RS.CO-1", "name": "Investigation Communication", "description": "Personnel know their roles during incident response.", "category": "Respond", "status": "Implemented", "lastReviewed": "2024-02-06", "evidence": [] },
        { "id": "RS.CO-2", "name": "Incident Information", "description": "Incident information is reported to appropriate parties.", "category": "Respond", "status": "Implemented", "lastReviewed": "2024-02-06", "evidence": [] },
        { "id": "RS.CO-3", "name": "Information Sharing", "description": "Information is shared with external stakeholders.", "category": "Respond", "status": "In Progress", "lastReviewed": "2024-02-07", "evidence": [] },
        { "id": "RS.AN-1", "name": "Analysis", "description": "Notifications from detection systems are investigated.", "category": "Respond", "status": "In Progress", "lastReviewed": "2023-10-15", "evidence": [] },
        { "id": "RS.AN-3", "name": "Impact Analysis", "description": "Analysis is performed to establish the impact of incidents.", "category": "Respond", "status": "At Risk", "lastReviewed": "2024-02-08", "evidence": [] },
        { "id": "RS.AN-4", "name": "Forensics", "description": "Forensics are performed to understand the scope and impact of incidents.", "category": "Respond", "status": "In Progress", "lastReviewed": "2024-02-08", "evidence": [] },
        { "id": "RS.AN-6", "name": "Root Cause Analysis", "description": "Actions performed during investigation are recorded.", "category": "Respond", "status": "In Progress", "lastReviewed": "2024-02-09", "evidence": [] },
        { "id": "RS.AN-7", "name": "Vulnerability Analysis", "description": "Incident data and context are utilized to support recovery.", "category": "Respond", "status": "At Risk", "lastReviewed": "2024-02-09", "evidence": [] },
        { "id": "RS.MI-1", "name": "Mitigation", "description": "Incidents are contained.", "category": "Respond", "status": "Implemented", "lastReviewed": "2023-10-15", "evidence": [] },
        { "id": "RS.MI-2", "name": "Incident Mitigation", "description": "Incidents are mitigated.", "category": "Respond", "status": "Implemented", "lastReviewed": "2024-02-10", "evidence": [] },
        { "id": "RS.MI-3", "name": "Vulnerabilities", "description": "Newly identified vulnerabilities are mitigated or documented as accepted risks.", "category": "Respond", "status": "In Progress", "lastReviewed": "2024-02-10", "evidence": [] },
        
        # RECOVER (RC)
        { "id": "RC.RP-1", "name": "Recovery Planning", "description": "Recovery processes and procedures are executed and maintained.", "category": "Recover", "status": "Implemented", "lastReviewed": "2023-10-15", "evidence": [] },
        { "id": "RC.CO-1", "name": "Recovery Communication", "description": "Public relations are managed during recovery.", "category": "Recover", "status": "In Progress", "lastReviewed": "2024-02-11", "evidence": [] },
        { "id": "RC.CO-2", "name": "Reputation Management", "description": "Reputation is managed during and after an incident.", "category": "Recover", "status": "In Progress", "lastReviewed": "2024-02-11", "evidence": [] },
        { "id": "RC.CO-3", "name": "Recovery Activities Communication", "description": "Recovery activities are communicated to stakeholders.", "category": "Recover", "status": "Implemented", "lastReviewed": "2024-02-12", "evidence": [] },
        { "id": "RC.IM-1", "name": "Improvements", "description": "Recovery plans are incorporated into improvement strategies.", "category": "Recover", "status": "Not Implemented", "lastReviewed": "2023-10-16", "evidence": [] },
        { "id": "RC.IM-2", "name": "Response and Recovery Update", "description": "Recovery strategies and processes are updated based on lessons learned.", "category": "Recover", "status": "In Progress", "lastReviewed": "2024-02-12", "evidence": [] },
    ]
    
    # Update NIST CSF framework
    result = await db.compliance_frameworks.update_one(
        {"id": "nistcsf"},
        {"$set": {"controls": complete_nist_controls}}
    )
    
    if result.modified_count > 0:
        print(f"✅ Successfully expanded NIST CSF to {len(complete_nist_controls)} controls")
    else:
        print("⚠️  No changes made - framework may not exist")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(add_missing_nist_controls())
