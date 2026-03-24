"""
Agent Instruction Endpoints
Manages deployment instructions sent to agents
"""

# Add these endpoints to app.py

@app.get("/api/agents/{agent_id}/instructions")
async def get_agent_instructions(agent_id: str):
    """
    Agent polls this endpoint to get pending instructions
    Returns list of instructions to execute
    """
    db = get_database()
    
    # Find pending instructions for this agent
    # Try by ID first, then by hostname
    agent = await db.agents.find_one({"$or": [{"id": agent_id}, {"hostname": agent_id}]})
    if agent:
        actual_agent_id = agent["id"]
    else:
        actual_agent_id = agent_id

    instructions = await db.agent_instructions.find({
        "agent_id": actual_agent_id,
        "status": "pending"
    }).to_list(length=100)
    
    # Mark as delivered
    for instruction in instructions:
        await db.agent_instructions.update_one(
            {"_id": instruction["_id"]},
            {"$set": {"status": "delivered", "delivered_at": datetime.now(timezone.utc).isoformat()}}
        )
    
    # Return instructions without MongoDB _id
    return [
        {
            "id": instr.get("id"),
            "type": instr.get("type"),
            "instruction": instr.get("instruction"),
            "patches": instr.get("patches", []),
            "job_id": instr.get("job_id")
        }
        for instr in instructions
    ]


@app.post("/api/deployments/{job_id}/result")
async def receive_deployment_result(job_id: str, data: dict[str, Any]):
    """
    Agent reports deployment result back
    Updates job status based on actual installation outcomes
    """
    db = get_database()
    
    print(f"[Deployment] Received result for job {job_id}: {data.get('status')}")
    
    # Extract result data
    status = data.get("status", "failed")  # completed, partial, failed
    results = data.get("results", [])
    successful = data.get("successful", 0)
    failed = data.get("failed", 0)
    total = data.get("total", 0)
    
    # Map agent status to job status
    if status == "completed":
        job_status = "Completed"
    elif status == "partial":
        job_status = "Partially Completed"
    else:
        job_status = "Failed"
    
    # Build status log from individual patch results
    status_log = []
    for result in results:
        log_entry = {
            "timestamp": result.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "message": f"{result.get('patch_id')}: {result.get('message')}",
            "level": "error" if result.get("status") == "failed" else "info"
        }
        status_log.append(log_entry)
    
    # Add summary log
    summary_log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": f"Deployment complete: {successful}/{total} successful, {failed}/{total} failed"
    }
    status_log.append(summary_log)
    
    # Update job in database
    update_data = {
        "status": job_status,
        "progress": 100,
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "actualResults": data,  # Store full agent response
    }
    
    # Try patch deployment jobs first
    result = await db.patch_deployment_jobs.update_one(
        {"id": job_id},
        {
            "$set": update_data,
            "$push": {"statusLog": {"$each": status_log}}
        }
    )
    
    # If not found in patch jobs, try software deployment jobs
    if result.matched_count == 0:
        await db.software_deployment_jobs.update_one(
            {"id": job_id},
            {
                "$set": update_data,
                "$push": {"statusLog": {"$each": status_log}}
            }
        )
    
    return {"status": "success", "message": "Result recorded"}
