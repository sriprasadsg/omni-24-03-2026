import motor.motor_asyncio
import asyncio
import datetime
import random

async def seed_runtime_security():
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb://localhost:27017')
    db = client['omni_platform']
    
    agent_id = "agent-8d86964b" # Active agent ID
    
    processes = [
        {"pid": 1, "name": "systemd", "user": "root", "cpu_percent": 0.1, "memory_percent": 0.5},
        {"pid": 501, "name": "nginx: master process", "user": "root", "cpu_percent": 0.0, "memory_percent": 1.2},
        {"pid": 502, "name": "nginx: worker process", "user": "www-data", "cpu_percent": 2.5, "memory_percent": 3.8},
        {"pid": 1024, "name": "python3 agent.py", "user": "omni", "cpu_percent": 5.2, "memory_percent": 8.4},
        {"pid": 2048, "name": "node server.js", "user": "omni", "cpu_percent": 12.4, "memory_percent": 15.2},
        {"pid": 4096, "name": "mongod", "user": "mongodb", "cpu_percent": 4.1, "memory_percent": 12.0},
        {"pid": 8192, "name": "redis-server", "user": "redis", "cpu_percent": 1.2, "memory_percent": 2.5},
        {"pid": 1234, "name": "ssh-keygen", "user": "attacker", "cpu_percent": 45.0, "memory_percent": 2.1},
        {"pid": 5678, "name": "nc -e /bin/sh", "user": "www-data", "cpu_percent": 1.0, "memory_percent": 0.5},
    ]
    
    connections = [
        {"local_address": "0.0.0.0", "local_port": 80, "remote_address": "0.0.0.0", "remote_port": 0, "status": "LISTEN", "pid": 501},
        {"local_address": "127.0.0.1", "local_port": 27017, "remote_address": "0.0.0.0", "remote_port": 0, "status": "LISTEN", "pid": 4096},
        {"local_address": "192.168.1.50", "local_port": 443, "remote_address": "104.22.3.41", "remote_port": 54321, "status": "ESTABLISHED", "pid": 502},
        {"local_address": "192.168.1.50", "local_port": 56789, "remote_address": "45.33.22.11", "remote_port": 4444, "status": "ESTABLISHED", "pid": 5678},
        {"local_address": "0.0.0.0", "local_port": 22, "remote_address": "0.0.0.0", "remote_port": 0, "status": "LISTEN", "pid": 1},
    ]
    
    suspicious_activities = [
        {
            "type": "Unauthorized Process",
            "description": "Reverse shell detected: nc -e /bin/sh running as www-data",
            "severity": "critical",
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
        },
        {
            "type": "Suspicious Connection",
            "description": "Outbound connection to known C2 IP: 45.33.22.11",
            "severity": "high",
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
        }
    ]
    
    runtime_security_data = {
        "processes": processes,
        "connections": connections,
        "suspicious_activities": suspicious_activities,
        "process_count": len(processes),
        "connection_count": len(connections)
    }
    
    # Update Agent
    result = await db.agents.update_one(
        {"id": agent_id},
        {
            "$set": {
                "meta.runtime_security": runtime_security_data
            }
        }
    )
    
    print(f"Updated agent {agent_id}: Matched={result.matched_count}, Modified={result.modified_count}")

if __name__ == "__main__":
    asyncio.run(seed_runtime_security())
