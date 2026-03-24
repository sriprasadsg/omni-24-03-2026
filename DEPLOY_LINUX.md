# Enterprise Omni-Agent Platform - Linux Deployment Guide

This guide describes how to set up and run the platform on a Linux environment (Ubuntu/Debian/CentOS/Fedora).

## Prerequisites

Ensure the following are installed:
1.  **Python 3.8+** (`python3 --version`)
2.  **Node.js 18+** & **npm** (`node -v`, `npm -v`)
3.  **Git**

## Setup Instructions

### 1. Clone & Prepare
```bash
# Navigate to project root
cd enterprise-omni-agent-ai-platform
```

### 2. Backend Setup
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Ensure slowapi is installed if not in requirements
pip install slowapi
deactivate
cd ..
```

### 3. Agent Setup
```bash
cd agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
cd ..
```

### 4. Frontend Setup
```bash
npm install
```

## Running the Platform

Use the provided shell script to start all services properly:

```bash
chmod +x start-all-services.sh
./start-all-services.sh
```

This will launch:
- **Backend**: http://127.0.0.1:5000
- **Frontend**: http://127.0.0.1:3000
- **Agent**: (Background Process)

Press `Ctrl+C` to stop all services simultaneously.
