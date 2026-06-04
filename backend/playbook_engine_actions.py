"""
PlaybookActionsMixin — default action implementations for PlaybookExecutionEngine.
All methods reference self.db and self.logger, which are set by PlaybookExecutionEngine.__init__.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict


class PlaybookActionsMixin:
    """Mixin providing all built-in _action_* handlers."""

    async def _action_log(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        message = params.get("message", "")
        level = params.get("level", "info")
        if level == "info":
            self.logger.info(message)
        elif level == "warning":
            self.logger.warning(message)
        elif level == "error":
            self.logger.error(message)
        return f"Logged: {message}"

    async def _action_http_request(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Make an HTTP request via httpx."""
        import httpx
        method  = params.get("method", "GET").upper()
        url     = params.get("url", "")
        headers = params.get("headers", {})
        body    = params.get("body") or params.get("json")
        timeout = float(params.get("timeout", 30))

        if not url:
            raise ValueError("http_request action requires 'url' parameter")

        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "POST":
                resp = await client.post(url, headers=headers, json=body)
            elif method == "PUT":
                resp = await client.put(url, headers=headers, json=body)
            elif method == "PATCH":
                resp = await client.patch(url, headers=headers, json=body)
            elif method == "DELETE":
                resp = await client.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text

        return {"status_code": resp.status_code, "ok": resp.is_success, "body": resp_body}

    async def _action_send_notification(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        channel    = params.get("channel", "email")
        message    = params.get("message", "")
        recipients = params.get("recipients", [])
        notification = {
            "channel": channel,
            "message": message,
            "recipients": recipients,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "execution_id": context.get("execution_id"),
        }
        await self.db.playbook_notifications.insert_one(notification)
        return f"Notification sent via {channel}"

    async def _action_create_ticket(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Create a ticket via the configured SOAR integration (Jira / ServiceNow fallback to DB)."""
        title       = params.get("title", "Security Incident")
        description = params.get("description", "")
        priority    = params.get("priority", "Medium")
        system      = params.get("system", "jira").lower()

        for k, v in (context.get("variables") or {}).items():
            description = description.replace(f"{{{{{k}}}}}", str(v))

        try:
            from soar_integrations import get_integration_manager
            mgr = get_integration_manager()
            connector = mgr.get_connector(system)
            if connector:
                result = await connector.execute("create_ticket", {
                    "title": title, "description": description, "priority": priority,
                    "project_key": params.get("project_key"),
                    "issue_type": params.get("issue_type", "Task"),
                })
                if result.get("status") == "success":
                    self.logger.info("Ticket created: %s", result.get("ticket_id"))
                    return f"Ticket created: {result.get('ticket_id')} — {result.get('ticket_url', '')}"
        except Exception as exc:
            self.logger.warning("SOAR ticket creation failed: %s — persisting to DB", exc)

        import uuid as _uuid
        ticket_id = f"LOCAL-{_uuid.uuid4().hex[:8].upper()}"
        await self.db.pending_tickets.insert_one({
            "ticket_id": ticket_id, "system": system, "title": title,
            "description": description, "priority": priority,
            "execution_id": context.get("execution_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "soar_unavailable",
        })
        return f"Ticket queued locally as {ticket_id} ({system} unavailable)"

    async def _action_block_ip(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Block an IP address by queuing a block_ip response task on the target agent."""
        ip = params.get("ip") or (context["variables"].get("trigger") or {}).get("source_ip")
        agent_id = (
            params.get("agent_id")
            or (context["variables"].get("trigger") or {}).get("agent_id")
        )
        if not ip or not agent_id:
            raise ValueError("block_ip requires 'ip' and 'agent_id'")

        since = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        dup = await self.db.response_tasks.find_one({
            "action": "block_ip", "params.ip": ip,
            "status": {"$in": ["queued", "executed"]},
            "created_at": {"$gte": since},
        })
        if dup:
            self.logger.info("DEDUP: block_ip for %s already queued, skipping", ip)
            return f"block_ip for {ip} already queued (deduplicated)"

        task = {
            "task_id": f"PB-BLK-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "agent_id": agent_id,
            "action": "block_ip",
            "params": {"ip": ip, "reason": params.get("reason", "playbook-auto")},
            "triggered_by_playbook": context.get("execution_id"),
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "executed_at": None, "result": None,
        }
        await self.db.response_tasks.insert_one(task)
        self.logger.info("Playbook queued block_ip task for IP %s on agent %s", ip, agent_id)
        return f"block_ip task queued for {ip} on agent {agent_id}"

    async def _action_isolate_endpoint(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Isolate an endpoint with safety gate before queuing the response task."""
        agent_id = (
            params.get("agent_id") or params.get("endpoint_id")
            or (context["variables"].get("trigger") or {}).get("agent_id")
        )
        if not agent_id:
            raise ValueError("isolate_endpoint requires 'agent_id' or 'endpoint_id'")

        execution_id = context.get("execution_id", "")
        gate = await self._gate_high_risk_action(
            "isolate_host", agent_id, context, execution_id,
            step_index=context.get("_current_step_index", 0), step=params,
        )
        if gate is not None:
            return gate  # type: ignore[return-value]

        task = {
            "task_id": f"PB-ISO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "agent_id": agent_id, "action": "isolate_host",
            "params": {"reason": params.get("reason", "playbook-auto")},
            "triggered_by_playbook": execution_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "executed_at": None, "result": None,
        }
        await self.db.response_tasks.insert_one(task)
        self.logger.info("Playbook queued isolate_host task for agent %s", agent_id)
        return f"isolate_host task queued for agent {agent_id}"

    async def _action_quarantine_file(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Quarantine a file by queuing a quarantine_file response task on the target agent."""
        file_path = (
            params.get("file_path")
            or (context["variables"].get("trigger") or {}).get("process", {}).get("path")
        )
        agent_id = (
            params.get("agent_id")
            or (context["variables"].get("trigger") or {}).get("agent_id")
        )
        if not file_path or not agent_id:
            raise ValueError("quarantine_file requires 'file_path' and 'agent_id'")

        task = {
            "task_id": f"PB-QRN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "agent_id": agent_id, "action": "quarantine_file",
            "params": {"file_path": file_path, "reason": params.get("reason", "playbook-auto")},
            "triggered_by_playbook": context.get("execution_id"),
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "executed_at": None, "result": None,
        }
        await self.db.response_tasks.insert_one(task)
        self.logger.info("Playbook queued quarantine_file task for %s on agent %s", file_path, agent_id)
        return f"quarantine_file task queued for {file_path} on agent {agent_id}"

    async def _action_rollback_ransomware(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Queue a rollback_ransomware task (VSS restore). Runs safety gate first."""
        agent_id = (
            params.get("agent_id")
            or (context["variables"].get("trigger") or {}).get("agent_id")
        )
        if not agent_id:
            raise ValueError("rollback_ransomware requires 'agent_id'")

        execution_id = context.get("execution_id", "")
        gate = await self._gate_high_risk_action(
            "rollback_ransomware", agent_id, context, execution_id,
            step_index=context.get("_current_step_index", 0), step=params,
        )
        if gate is not None:
            return gate  # type: ignore[return-value]

        task = {
            "task_id": f"PB-RRB-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "agent_id": agent_id, "action": "rollback_ransomware",
            "params": {
                "volume": params.get("volume", "C:"),
                "reason": params.get("reason", "playbook-auto: ransomware rollback"),
            },
            "triggered_by_playbook": execution_id,
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "executed_at": None, "result": None,
        }
        await self.db.response_tasks.insert_one(task)
        self.logger.info("Playbook queued rollback_ransomware task for agent %s", agent_id)
        return f"rollback_ransomware task queued for agent {agent_id}"

    async def _action_send_email(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Send an email via SMTP (config from environment) or log to DB as fallback."""
        import os
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        to_list: list = params.get("to") or []
        if isinstance(to_list, str):
            to_list = [t.strip() for t in to_list.split(",")]
        subject: str = params.get("subject", "Security Alert")
        body: str    = params.get("body", "")

        for k, v in (context.get("variables") or {}).items():
            body = body.replace(f"{{{{{k}}}}}", str(v))

        smtp_host = os.environ.get("SMTP_HOST", "")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")
        smtp_from = os.environ.get("SMTP_FROM", smtp_user)

        if smtp_host and smtp_user and to_list:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"]    = smtp_from
                msg["To"]      = ", ".join(to_list)
                msg.attach(MIMEText(body, "plain"))

                def _smtp_send():
                    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as srv:
                        srv.starttls()
                        if smtp_pass:
                            srv.login(smtp_user, smtp_pass)
                        srv.sendmail(smtp_from, to_list, msg.as_string())

                await asyncio.to_thread(_smtp_send)
                self.logger.info("Email sent to %s: %s", to_list, subject)
                return f"Email sent to {', '.join(to_list)}"
            except Exception as exc:
                self.logger.warning("SMTP send failed: %s — storing in DB for review", exc)

        await self.db.pending_notifications.insert_one({
            "channel": "email", "to": to_list, "subject": subject, "body": body,
            "execution_id": context.get("execution_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "smtp_unavailable",
        })
        return f"Email queued (SMTP not configured) for {', '.join(to_list)}"

    async def _action_wait(self, params: Dict[str, Any], context: Dict[str, Any]) -> str:
        seconds = params.get("seconds", 0)
        await asyncio.sleep(seconds)
        return f"Waited {seconds} seconds"

    async def _action_set_variable(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        name  = params.get("name")
        value = params.get("value")
        context["variables"][name] = value
        return value
