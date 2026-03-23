# Enterprise Omni-Agent AI Platform

A production-ready, enterprise-grade autonomous observability and AI governance platform that combines intelligent monitoring with responsible AI management, featuring real-time dashboards, AI-driven insights, and comprehensive compliance tracking.

## Getting Started

This application is a demonstration of a multi-tenant enterprise platform. You can log in using one of the pre-configured user accounts below to explore the features available to different roles.

### Login Credentials

All users share the same password for this demonstration.

**Password:** `password123`

| Name             | Email                  | Role              | Tenant      | Status    |
| ---------------- | ---------------------- | ----------------- | ----------- | --------- |
| Super Admin      | `super@omni.ai`        | Super Admin       | Platform    | Active    |
| Alice Admin      | `alice@acme.com`       | Tenant Admin      | Acme Corp   | Active    |
| Bob Security     | `bob@acme.com`         | SecOps Analyst    | Acme Corp   | Active    |
| Charlie DevOps   | `charlie@acme.com`     | DevOps Engineer   | *Disabled*  |
| Eve Engineer     | `eve@initech.com`      | Tenant Admin      | Initech     | Active    |

### Self-Service Registration

You can also register a new company (tenant) and a corresponding administrator account directly from the login screen.

1.  Navigate to the login page.
2.  Click on "Sign Up".
3.  Fill in your company name, your name, email, and a password.
4.  Upon successful registration, you will be automatically logged in as the "Tenant Admin" for your new workspace.

## Key Features

The platform is a comprehensive, multi-tenant solution designed to provide a single pane of glass for modern IT operations, security, and governance.

### Core Platform & UI/UX

*   **Multi-Tenancy Architecture:** Full data segregation between customer tenants, with a Super Admin role for platform-wide management.
*   **Authentication & Authorization:** Secure login system with self-service workspace registration and a granular Role-Based Access Control (RBAC) engine.
*   **Interactive Guided Tour:** An animated AI character, "Omni," provides a step-by-step tour of the platform's features and navigates users between pages.
*   **Customizable UI:** Features a full Light/Dark mode and a collapsible sidebar with organized, expandable sections for easy navigation.
*   **CXOs Dashboard:** An exclusive, high-level dashboard for executives with multiple switchable themes (Focus, Matrix, Executive, Glass, Strategic) to present strategic KPIs.
*   **Real-time Notifications:** A centralized notification system keeps users informed of important events.
*   **Local Persistence:** Uses browser `localStorage` to simulate a database, ensuring all data and configurations persist across page reloads.

### AI-Powered Autonomous Operations

*   **AI Command Bar (`Cmd+K`):** Use natural language to navigate the app, apply filters, and execute commands.
*   **Context-Aware AI Chat Assistant:** A floating chat assistant that has context on the current dashboard, allowing users to ask questions about the on-screen data.
*   **AI-Driven Analysis:** AI-generated insights and summaries are available on dashboards for Health, Security, and FinOps, correlating metrics and events to provide actionable recommendations.
*   **Autonomous Remediation:** The platform can autonomously diagnose and remediate agent errors, CSPM findings, and AI system risks, with detailed agentic step-by-step logging.
*   **AI-Generated SOAR Playbooks:** Generate security automation playbooks from a natural language prompt.
*   **AI-Powered Code Correction:** Automatically generate secure code fixes for vulnerabilities found during Static Application Security Testing (SAST).

### Unified Observability

*   **Agent Fleet Management:** A central dashboard to monitor, manage, and install agents across various platforms (Linux, Windows, Kubernetes). Includes remote actions, capability management, and a version upgrade manager.
*   **Asset Management:** A complete inventory of all hardware and software assets, with detailed views, vulnerability scanning, and File Integrity Monitoring (FIM).
*   **Log Explorer:** A centralized interface to search, filter, and analyze logs from all services and agents.
*   **Distributed Tracing:** Visualize request flows and service dependencies in a microservices architecture to identify performance bottlenecks.
*   **Network Observability:** Agentless monitoring for network devices (routers, switches, firewalls) with configuration change tracking and vulnerability detection.
*   **Proactive Insights:** AI-driven dashboard for predictive alerts, anomaly detection, and automated Root Cause Analysis (RCA).

### Comprehensive Security (XDR, SIEM & SOAR)

*   **Security Operations Center (SOC):** A unified dashboard for SIEM and SOAR, featuring a live security event feed, case management, and playbook automation.
*   **Threat Hunting (UEBA):** Proactively identifies insider threats and compromised accounts using User and Entity Behavior Analytics.
*   **Cloud Security Posture Management (CSPM):** Continuously monitor cloud accounts (AWS, Azure, GCP) for misconfigurations and security risks, with AI-generated remediation guides.
*   **Data Security Posture Management (DSPM):** Discover, classify, and protect sensitive data (PII, Financial, IP) across all enterprise assets.
*   **Attack Path Analysis:** Visualize potential adversary paths from points of entry to critical "crown jewel" assets.
*   **Patch Management:** A dedicated dashboard to monitor and deploy security patches across all managed assets, with job scheduling and tracking.
*   **Live Threat Intelligence:** Integrates with threat intelligence feeds (like VirusTotal) to scan artifacts (IPs, domains, hashes) in real-time.
*   **Incident Impact Analysis:** Automatically generates a "blast radius" graph to visualize the potential business and service impact of a security alert or case.

### DevSecOps & Platform Engineering

*   **DevSecOps Dashboard:** A "shift-left" security dashboard that provides insights from SAST and Software Bill of Materials (SBOM) analysis.
*   **Static Application Security Testing (SAST):** Scans code repositories for vulnerabilities and provides AI-powered code fixes.
*   **Software Supply Chain Security (SBOM):** Upload and analyze SBOM files to identify components and their associated vulnerabilities.
*   **DORA Metrics:** Track key DevOps performance indicators: Deployment Frequency, Lead Time for Changes, Change Failure Rate, and Mean Time to Recovery.
*   **Service Catalog (IDP):** An Internal Developer Platform where developers can provision new services using approved, secure-by-default templates.
*   **Chaos Engineering:** Proactively test system resilience by running controlled failure experiments (e.g., CPU Hog, Latency Injection).
*   **Developer Hub:** Centralized API documentation for all platform services to enable custom integrations.

### Governance, Risk, and Compliance (GRC)

*   **Compliance Management:** Track and manage compliance against major frameworks like SOC 2, ISO 27001, GDPR, HIPAA, PCI DSS, and NIST CSF.
*   **AI Governance (ISO 42001):** A dedicated dashboard to manage the entire AI lifecycle, including an AI System Registry, impact assessments, fairness metrics, risk management, and a model registry.
*   **Audit Log:** An immutable, searchable log of all significant user and system actions for security and compliance audits.
*   **Automation Policies:** Define rules for when and how the platform can take autonomous actions, ensuring human-in-the-loop control.

### Administration & Management

*   **Tenant Management:** A Super Admin dashboard to oversee all customer tenants, manage subscriptions, and monitor platform-wide resource usage.
*   **Settings Dashboard:** A centralized hub for all configurations, including:
    *   **User Management & RBAC:** Create, edit, and disable users; create and manage custom roles with granular permissions.
    *   **API Key Management:** Generate and revoke API keys for programmatic access.
    *   **Integrations Marketplace:** Configure third-party integrations (e.g., Slack, Jira, PagerDuty).
    *   **Subscription Management:** Admins can manage the features enabled for their tenant.
*   **FinOps & Billing:** Monitor cloud resource consumption and costs with AI-powered analysis and cost-saving recommendations.
*   **User Profile Management:** Users can edit their personal information and avatar.

## Technology Stack

-   **Frontend**: React, TypeScript, Tailwind CSS
-   **AI Integration**: Google Gemini API
-   **Charting**: Recharts
#   1 5 - 1 2 - 2 0 2 5  
 #   o m n i  
 #   o m n i - 2 4 - 0 3 - 2 0 2 6  
 