import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List, Dict
import secrets
import hashlib
from datetime import datetime, timedelta
from jinja2 import Template
from cryptography.fernet import Fernet
import os
import base64

# Email service for sending notifications
class EmailService:
    def __init__(self):
        # Generate or load encryption key for SMTP passwords
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher = Fernet(self.encryption_key)
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key for SMTP passwords"""
        key_file = 'email_encryption.key'
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            return key
    
    def encrypt_password(self, password: str) -> str:
        """Encrypt SMTP password"""
        encrypted = self.cipher.encrypt(password.encode())
        return base64.b64encode(encrypted).decode()
    
    def decrypt_password(self, encrypted_password: str) -> str:
        """Decrypt SMTP password"""
        encrypted = base64.b64decode(encrypted_password.encode())
        decrypted = self.cipher.decrypt(encrypted)
        return decrypted.decode()
    
    def send_email(
        self,
        smtp_config: Dict,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        attachments: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Send email using provided SMTP configuration
        
        Args:
            smtp_config: SMTP configuration dict with host, port, user, password, etc.
            to_email: Recipient email address
            subject: Email subject
            body_text: Plain text body
            body_html: HTML body (optional)
            attachments: List of attachments (optional)
        
        Returns:
            Dict with success status and message
        """
        try:
            # Create message
            message = MIMEMultipart('alternative')
            message['From'] = f"{smtp_config.get('fromName', 'Omni-Agent')} <{smtp_config.get('fromEmail', smtp_config['smtpUser'])}>"
            message['To'] = to_email
            message['Subject'] = subject
            
            # Add text and HTML parts
            message.attach(MIMEText(body_text, 'plain'))
            if body_html:
                message.attach(MIMEText(body_html, 'html'))
            
            # Add attachments if provided
            if attachments:
                for attachment in attachments:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment['data'])
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f"attachment; filename= {attachment['filename']}")
                    message.attach(part)
            
            # Decrypt password
            smtp_password = self.decrypt_password(smtp_config['smtpPasswordEncrypted'])
            
            # Create SMTP connection
            context = ssl.create_default_context()
            
            if smtp_config.get('useTLS', True):
                # Use STARTTLS
                with smtplib.SMTP(smtp_config['smtpHost'], smtp_config['smtpPort']) as server:
                    server.starttls(context=context)
                    server.login(smtp_config['smtpUser'], smtp_password)
                    server.send_message(message)
            else:
                # Use SSL
                with smtplib.SMTP_SSL(smtp_config['smtpHost'], smtp_config['smtpPort'], context=context) as server:
                    server.login(smtp_config['smtpUser'], smtp_password)
                    server.send_message(message)
            
            return {
                'success': True,
                'message': 'Email sent successfully'
            }
        
        except Exception as e:
            return {
                'success': False,
                'message': f'Failed to send email: {str(e)}'
            }
    
    def verify_smtp_config(self, smtp_config: Dict) -> Dict:
        """
        Test SMTP configuration by attempting to connect
        
        Args:
            smtp_config: SMTP configuration dict
        
        Returns:
            Dict with success status and message
        """
        try:
            smtp_password = self.decrypt_password(smtp_config['smtpPasswordEncrypted'])
            context = ssl.create_default_context()
            
            if smtp_config.get('useTLS', True):
                with smtplib.SMTP(smtp_config['smtpHost'], smtp_config['smtpPort'], timeout=10) as server:
                    server.starttls(context=context)
                    server.login(smtp_config['smtpUser'], smtp_password)
            else:
                with smtplib.SMTP_SSL(smtp_config['smtpHost'], smtp_config['smtpPort'], context=context, timeout=10) as server:
                    server.login(smtp_config['smtpUser'], smtp_password)
            
            return {
                'success': True,
                'message': 'SMTP configuration is valid'
            }
        
        except Exception as e:
            return {
                'success': False,
                'message': f'SMTP configuration error: {str(e)}'
            }
    
    def generate_verification_token(self) -> str:
        """Generate a secure verification token"""
        return secrets.token_urlsafe(32)
    
    def hash_token(self, token: str) -> str:
        """Hash a token for storage"""
        return hashlib.sha256(token.encode()).hexdigest()
    
    def send_verification_email(self, smtp_config: Dict, user_email: str, user_name: str, token: str, base_url: str) -> Dict:
        """Send email verification email"""
        verification_link = f"{base_url}/verify-email?token={token}"
        
        body_text = f"""
Hello {user_name},

Welcome to the Omni-Agent AI Platform!

Please verify your email address by clicking the link below:
{verification_link}

This link will expire in 24 hours.

If you didn't create an account, please ignore this email.

Best regards,
The Omni-Agent Team
"""
        
        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
        .button {{ display: inline-block; padding: 12px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
        .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Welcome to Omni-Agent!</h1>
        </div>
        <div class="content">
            <p>Hello {user_name},</p>
            <p>Thank you for signing up for the Omni-Agent AI Platform. To complete your registration, please verify your email address.</p>
            <p style="text-align: center;">
                <a href="{verification_link}" class="button">Verify Email Address</a>
            </p>
            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #667eea;">{verification_link}</p>
            <p><strong>This link will expire in 24 hours.</strong></p>
            <p>If you didn't create an account, please ignore this email.</p>
        </div>
        <div class="footer">
            <p>© 2025 Omni-Agent AI Platform. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""
        
        return self.send_email(
            smtp_config=smtp_config,
            to_email=user_email,
            subject="Verify your email address - Omni-Agent",
            body_text=body_text,
            body_html=body_html
        )
    
    def send_welcome_email(self, smtp_config: Dict, user_email: str, user_name: str, tenant_name: str) -> Dict:
        """Send welcome email to new user"""
        body_text = f"""
Hello {user_name},

Welcome to {tenant_name} on the Omni-Agent AI Platform!

Your account has been successfully created. You can now:
- Monitor your infrastructure security
- Track compliance across frameworks
- Manage vulnerabilities
- View real-time analytics

Get started by logging in to your dashboard.

Best regards,
The Omni-Agent Team
"""
        
        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
        .feature {{ padding: 15px; margin: 10px 0; background: white; border-left: 4px solid #667eea; }}
        .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Welcome to Omni-Agent!</h1>
        </div>
        <div class="content">
            <p>Hello {user_name},</p>
            <p>Your account for <strong>{tenant_name}</strong> has been successfully created!</p>
            <h3>What you can do:</h3>
            <div class="feature">
                <strong>🛡️ Security Monitoring</strong><br>
                Monitor your infrastructure security in real-time
            </div>
            <div class="feature">
                <strong>📊 Compliance Tracking</strong><br>
                Track compliance across multiple frameworks
            </div>
            <div class="feature">
                <strong>🔍 Vulnerability Management</strong><br>
                Identify and remediate vulnerabilities
            </div>
            <div class="feature">
                <strong>📈 Analytics & Reporting</strong><br>
                View comprehensive analytics and generate reports
            </div>
            <p>Ready to get started? Log in to your dashboard and explore!</p>
        </div>
        <div class="footer">
            <p>© 2025 Omni-Agent AI Platform. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""
        
        return self.send_email(
            smtp_config=smtp_config,
            to_email=user_email,
            subject=f"Welcome to {tenant_name} - Omni-Agent",
            body_text=body_text,
            body_html=body_html
        )
    
    def send_alert_notification(self, smtp_config: Dict, recipients: List[str], alert: Dict) -> Dict:
        """Send security alert notification"""
        severity_colors = {
            'critical': '#dc2626',
            'high': '#ea580c',
            'medium': '#f59e0b',
            'low': '#10b981'
        }
        
        severity = alert.get('severity', 'medium').lower()
        color = severity_colors.get(severity, '#6b7280')
        
        body_text = f"""
Security Alert: {alert.get('title', 'Unknown Alert')}

Severity: {severity.upper()}
Time: {alert.get('timestamp', 'Unknown')}
Asset: {alert.get('asset', 'Unknown')}

Description:
{alert.get('description', 'No description available')}

Recommended Actions:
{alert.get('recommendations', 'No recommendations available')}

View full details in your dashboard.
"""
        
        body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: {color}; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
        .alert-box {{ background: white; border-left: 4px solid {color}; padding: 15px; margin: 15px 0; }}
        .severity {{ display: inline-block; padding: 5px 15px; background: {color}; color: white; border-radius: 20px; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚨 Security Alert</h1>
        </div>
        <div class="content">
            <h2>{alert.get('title', 'Unknown Alert')}</h2>
            <p><span class="severity">{severity.upper()}</span></p>
            <div class="alert-box">
                <p><strong>Time:</strong> {alert.get('timestamp', 'Unknown')}</p>
                <p><strong>Asset:</strong> {alert.get('asset', 'Unknown')}</p>
                <p><strong>Description:</strong></p>
                <p>{alert.get('description', 'No description available')}</p>
                <p><strong>Recommended Actions:</strong></p>
                <p>{alert.get('recommendations', 'No recommendations available')}</p>
            </div>
            <p>View full details in your dashboard.</p>
        </div>
    </div>
</body>
</html>
"""
        
        # Send to all recipients
        results = []
        for recipient in recipients:
            result = self.send_email(
                smtp_config=smtp_config,
                to_email=recipient,
                subject=f"[{severity.upper()}] Security Alert: {alert.get('title', 'Unknown')}",
                body_text=body_text,
                body_html=body_html
            )
            results.append(result)
        
        # Return success if at least one email sent
        success_count = sum(1 for r in results if r['success'])
        return {
            'success': success_count > 0,
            'message': f'Sent to {success_count}/{len(recipients)} recipients',
            'results': results
        }

# Global email service instance
email_service = EmailService()
