
        
    async def _send_email(
        self,
        recipients: List[str],
        subject: str,
        body: str,
        severity: str
    ) -> Dict[str, Any]:
        """
        Send email notification using SMTP logic
        """
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import os
        import logging

        # 1. Config (Try Env Vars, else Mock)
        smtp_host = os.getenv("SMTP_HOST", "localhost")
        smtp_port = int(os.getenv("SMTP_PORT", "1025")) # Default to MailHog/Mock port
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")
        
        # If no host configured and not testing, log and return
        if smtp_host == "localhost" and not os.getenv("FORCE_SMTP"):
             # Fallback to Logger
             with open("notifications.log", "a") as f:
                 f.write(f"[EMAIL] To: {recipients} | Subject: {subject} | Body: {body[:50]}...\n")
             return {
                 "success": True,
                 "provider": "logger",
                 "message": "Logged to file (SMTP not configured)"
             }
        
        try:
            msg = MIMEMultipart()
            msg['From'] = smtp_user or "alert@omni-agent.ai"
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = f"[{severity.upper()}] {subject}"
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Synchronous SMTP (Block briefly) or run in thread
            # For MVP, sync is acceptable if volume is low
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if smtp_user and smtp_pass:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                server.send_message(msg)
                
            return {
                "success": True,
                "provider": "smtp",
                "host": smtp_host
            }
        except Exception as e:
            # Fallback to Logger on basic error
             with open("notifications.log", "a") as f:
                 f.write(f"[EMAIL_FAIL] To: {recipients} | Error: {e}\n")
             return {
                "success": False,
                "error": str(e)
            }

    async def _send_sms(
        self,
        phone_numbers: List[str],
        message: str
    ) -> Dict[str, Any]:
        """
        Send SMS notification (Simulated via File Log)
        """
        # In production -> Client(twilio_sid, token).messages.create(...)
        
        # Simulate Gateway Latency
        import asyncio
        await asyncio.sleep(0.1)
        
        # Log to "Gateway"
        with open("sms_outbox.log", "a") as f:
            for number in phone_numbers:
                f.write(f"[SMS] To: {number} | Msg: {message}\n")
                
        return {
            "success": True,
            "provider": "file_gateway",
            "recipients": phone_numbers
        }
