"""
Notification subsystem: Windows Desktop Toast & Optional SMTP Email.
Strict Rule: No Telegram integration permitted.
"""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import os
import platform
import smtplib
import subprocess
from typing import Optional

logger = logging.getLogger("free_tier_hunter.notifier")


class Notifier:
    """Delivers critical capacity and provisioning alerts without exposing sensitive data."""

    def __init__(
        self,
        enable_desktop: bool = True,
        enable_email: bool = False,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_from: Optional[str] = None,
        notification_email: Optional[str] = None,
    ):
        self.enable_desktop = enable_desktop
        self.enable_email = enable_email
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.smtp_from = smtp_from or smtp_user
        self.notification_email = notification_email

    def notify(self, title: str, message: str, level: str = "INFO") -> None:
        """Dispatches an alert to configured notification channels."""
        # Sanitize message to never leak secrets
        clean_title = self._sanitize(title)
        clean_message = self._sanitize(message)

        logger.info(f"NOTIFICATION [{level}] {clean_title}: {clean_message}")

        if self.enable_desktop:
            self._send_desktop_notification(clean_title, clean_message)

        if self.enable_email:
            self._send_email_notification(clean_title, clean_message)

    def _sanitize(self, text: str) -> str:
        """Redacts potential private keys, passwords, and tokens."""
        if not text:
            return ""
        redacted = text
        for secret_phrase in ["BEGIN RSA PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY", "password"]:
            if secret_phrase in redacted:
                redacted = redacted.replace(secret_phrase, "[REDACTED]")
        return redacted

    def _send_desktop_notification(self, title: str, message: str) -> None:
        """Sends native desktop notification on Windows via PowerShell toast."""
        try:
            if platform.system() == "Windows":
                # Escape single quotes for PowerShell
                ps_title = title.replace("'", "''")
                ps_message = message.replace("'", "''")
                ps_command = f"""
                [void] [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms')
                $notify = New-Object System.Windows.Forms.NotifyIcon
                $notify.Icon = [System.Drawing.SystemIcons]::Information
                $notify.BalloonTipTitle = '{ps_title}'
                $notify.BalloonTipText = '{ps_message}'
                $notify.BalloonTipIcon = 'Info'
                $notify.Visible = $True
                $notify.ShowBalloonTip(5000)
                """
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", ps_command],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
        except Exception as e:
            logger.debug(f"Failed to dispatch desktop toast: {e}")

    def _send_email_notification(self, title: str, message: str) -> None:
        """Dispatches SMTP email notification."""
        if not self.smtp_host or not self.notification_email:
            return

        try:
            msg = MIMEMultipart()
            msg["From"] = self.smtp_from or "hunter@localhost"
            msg["To"] = self.notification_email
            msg["Subject"] = f"[OCI Hunter] {title}"
            msg.attach(MIMEText(message, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            logger.info("Dispatched email notification successfully.")
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
