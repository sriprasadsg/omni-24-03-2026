"""Compliance control definitions: SOC 1, SOC 3, SOC for Cybersecurity."""

from seed_compliance_controls_a import ctrl


# SOC 1 controls – ITGC domains for ICFR (used by both Type I and Type II)
SOC1_CONTROLS = [
    ctrl("SOC1-CE.1","Control Environment Policy","Management demonstrates commitment to integrity and ethical values through documented policies.","Control Environment"),
    ctrl("SOC1-CE.2","Organisational Structure","Reporting lines, authorities, and responsibilities are defined for financial processing functions.","Control Environment"),
    ctrl("SOC1-CE.3","Board Oversight","The board or audit committee provides oversight of financial controls and associated IT general controls.","Control Environment"),
    ctrl("SOC1-CE.4","Competence Requirements","Personnel responsible for financial systems have sufficient competence to perform their duties.","Control Environment"),
    ctrl("SOC1-CE.5","Accountability","Management holds individuals accountable for internal control responsibilities.","Control Environment"),
    ctrl("SOC1-LA.1","User Access Provisioning","Formal process exists for granting access to financial and operational systems, including documented approval.","Logical Access"),
    ctrl("SOC1-LA.2","User Access Modification and Termination","Access is promptly modified or removed upon role change or termination for all financial systems.","Logical Access"),
    ctrl("SOC1-LA.3","Privileged Access Control","Privileged (administrator) access to systems supporting client financial reporting is restricted and reviewed.","Logical Access"),
    ctrl("SOC1-LA.4","Access Review","Periodic user access reviews are conducted for systems in scope; inappropriate access is remediated.","Logical Access"),
    ctrl("SOC1-LA.5","Segregation of Duties","Conflicting duties in financial processing workflows are separated across different individuals or roles.","Logical Access"),
    ctrl("SOC1-LA.6","Authentication Controls","Password and MFA requirements are enforced on systems supporting client financial reporting.","Logical Access"),
    ctrl("SOC1-CM.1","Change Management Policy","A formal change management policy governs all changes to financial applications, databases, and infrastructure.","Change Management"),
    ctrl("SOC1-CM.2","Change Authorization","Changes to in-scope systems require documented authorisation before implementation.","Change Management"),
    ctrl("SOC1-CM.3","Change Testing","Changes are tested in a non-production environment and results are reviewed before production deployment.","Change Management"),
    ctrl("SOC1-CM.4","Dev and Production Separation","Developers are prevented from migrating their own code changes to the production environment.","Change Management"),
    ctrl("SOC1-CM.5","Emergency Change Process","Emergency changes follow an expedited but documented and subsequently reviewed approval process.","Change Management"),
    ctrl("SOC1-CM.6","Release Management","Releases to production are scheduled, communicated, and verified post-deployment.","Change Management"),
    ctrl("SOC1-CO.1","Job Scheduling","Automated batch jobs supporting client transactions are scheduled, monitored, and exceptions resolved.","Computer Operations"),
    ctrl("SOC1-CO.2","Incident and Problem Management","Operational incidents affecting financial processing are logged, prioritised, and resolved with root-cause analysis.","Computer Operations"),
    ctrl("SOC1-CO.3","System Availability Monitoring","Availability and performance of in-scope systems are continuously monitored and alerting is configured.","Computer Operations"),
    ctrl("SOC1-CO.4","Capacity Management","System capacity is planned and monitored to ensure processing can meet demand without disruption.","Computer Operations"),
    ctrl("SOC1-BR.1","Backup Policy","Backup schedules, retention periods, and responsibilities are documented for all in-scope systems.","Backup and Recovery"),
    ctrl("SOC1-BR.2","Backup Execution Monitoring","Backup jobs are monitored for successful completion; failures are investigated and resolved promptly.","Backup and Recovery"),
    ctrl("SOC1-BR.3","Backup Restoration Testing","Restoration from backup is tested at least annually to confirm recoverability.","Backup and Recovery"),
    ctrl("SOC1-BR.4","Disaster Recovery Plan","A disaster recovery plan exists defining RTOs and RPOs for systems supporting client financial reporting.","Backup and Recovery"),
    ctrl("SOC1-BR.5","DR Testing","The disaster recovery plan is tested at least annually and results are documented with remediation of gaps.","Backup and Recovery"),
    ctrl("SOC1-PD.1","SDLC Policy","A system development life cycle policy governs the development and acquisition of new financial systems.","Program Development"),
    ctrl("SOC1-PD.2","Requirements and Design Review","Business and security requirements are documented and reviewed before development commences.","Program Development"),
    ctrl("SOC1-PD.3","Security Testing","Security and functionality testing are performed prior to production deployment of new systems.","Program Development"),
    ctrl("SOC1-PS.1","Physical Security of Data Centres","Physical access to data centres hosting in-scope systems is restricted, logged, and reviewed.","Physical Security"),
]


# SOC 3 controls – condensed public Trust Services Criteria summary
SOC3_CONTROLS = [
    ctrl("SOC3-CC","Security Commitment","The entity commits to protecting information from unauthorized access, disclosure, and misuse.","Security"),
    ctrl("SOC3-CC2","Communication of Security Policies","The entity communicates its security commitments to users.","Security"),
    ctrl("SOC3-CC3","Risk Assessment","The entity assesses risks to achieving its security objectives.","Security"),
    ctrl("SOC3-CC4","Monitoring","The entity monitors the effectiveness of its security controls on an ongoing basis.","Security"),
    ctrl("SOC3-CC6","Access Controls","The entity implements logical access security over protected information assets.","Security"),
    ctrl("SOC3-CC7","System Operations","The entity monitors for security anomalies and responds to incidents.","Security"),
    ctrl("SOC3-CC8","Change Management","The entity manages changes to prevent unauthorized alterations to system components.","Security"),
    ctrl("SOC3-A1","Availability Commitment","The entity commits to making systems available as agreed to in service commitments.","Availability"),
    ctrl("SOC3-A2","Capacity and Recovery","The entity maintains capacity and recovery capability to meet availability objectives.","Availability"),
    ctrl("SOC3-C1","Confidentiality Commitment","The entity identifies and protects confidential information as committed.","Confidentiality"),
    ctrl("SOC3-PI1","Processing Integrity Commitment","The entity processes information completely, accurately, validly, and timely.","Processing Integrity"),
    ctrl("SOC3-P1","Privacy Notice","The entity provides notice to data subjects about its privacy practices.","Privacy"),
    ctrl("SOC3-P2","Choice and Consent","The entity provides data subjects with choices regarding their personal information.","Privacy"),
    ctrl("SOC3-P3","Collection and Use","The entity collects and uses personal information in accordance with its stated commitments.","Privacy"),
    ctrl("SOC3-P8","Monitoring and Enforcement","The entity monitors compliance with its privacy commitments and provides recourse.","Privacy"),
]


# SOC for Cybersecurity controls – Description Criteria and Trust Services Criteria for cyber programs
SOC_CYBER_CONTROLS = [
    ctrl("SOCC-D1","Nature of Business and Operations","The entity describes the nature of its business and operations relevant to the cybersecurity risk management program.","Description Criteria"),
    ctrl("SOCC-D2","Principal Service Commitments","The entity describes its principal cybersecurity service commitments and system requirements.","Description Criteria"),
    ctrl("SOCC-D3","Components of the System","The entity describes the components of the system used to meet cybersecurity objectives.","Description Criteria"),
    ctrl("SOCC-D4","Boundaries of the System","The entity describes the boundaries of the system, including infrastructure, software, data, and people.","Description Criteria"),
    ctrl("SOCC-D5","Cybersecurity Risk Management Program","The entity describes its cybersecurity risk management program and how it meets its objectives.","Description Criteria"),
    ctrl("SOCC-CC.1","Control Environment for Cybersecurity","Management has established control environment policies specific to the cybersecurity program.","Risk Governance"),
    ctrl("SOCC-CC.2","Communication of Cybersecurity Policies","The entity communicates cybersecurity policies, roles, and responsibilities to relevant personnel.","Risk Governance"),
    ctrl("SOCC-CC.3","Cybersecurity Risk Assessment","The entity identifies and assesses cybersecurity risks to achieving its objectives.","Risk Governance"),
    ctrl("SOCC-CC.4","Monitoring of Cybersecurity Controls","The entity monitors the effectiveness of cybersecurity controls on an ongoing basis.","Risk Governance"),
    ctrl("SOCC-CC.5","Cybersecurity Control Activities","The entity deploys cybersecurity controls to mitigate identified risks to acceptable levels.","Risk Governance"),
    ctrl("SOCC-CC.6","Logical Access for Cybersecurity","Logical access controls are in place to prevent unauthorized access to critical cybersecurity assets.","Access and Protection"),
    ctrl("SOCC-CC.7","Threat Detection and Response","The entity detects cybersecurity threats and responds to incidents according to defined procedures.","Detection and Response"),
    ctrl("SOCC-CC.8","Change Management for Cybersecurity","Changes to cybersecurity-relevant system components are managed and controlled.","Detection and Response"),
    ctrl("SOCC-CC.9","Vendor and Business Partner Risk","Third-party cybersecurity risks are assessed and managed in vendor contracts and ongoing monitoring.","Third-Party Risk"),
    ctrl("SOCC-A1","Availability of Security Systems","Security monitoring and response systems are available to meet cybersecurity objectives.","Availability"),
    ctrl("SOCC-IR.1","Incident Response Plan","The entity has a documented cybersecurity incident response plan with defined roles and procedures.","Incident Response"),
    ctrl("SOCC-IR.2","Incident Identification and Analysis","Cybersecurity events are identified, classified, and analysed for potential impact.","Incident Response"),
    ctrl("SOCC-IR.3","Incident Containment and Eradication","Defined procedures for containing, eradicating, and recovering from cybersecurity incidents are in place.","Incident Response"),
    ctrl("SOCC-IR.4","Post-Incident Review","Post-incident reviews are conducted to improve cybersecurity controls and response capabilities.","Incident Response"),
    ctrl("SOCC-IR.5","Disclosure of Cybersecurity Incidents","Significant cybersecurity incidents are disclosed to relevant stakeholders and regulators as required.","Incident Response"),
]

