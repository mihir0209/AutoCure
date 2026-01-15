"""
Email Notifier Subprocess
Sends notifications about healing operations to admins.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime

from utils.logger import setup_colored_logger
from utils.models import HealingReport, FixProposal, ErrorInfo

logger = setup_colored_logger("email_notifier")


class EmailNotifier:
    """
    Handles email notifications for the Self-Healing System.
    
    Sends:
    - Fix proposals with git branch links
    - Test results
    - Severity assessments
    """
    
    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        sender_email: str,
        sender_password: str,  # App password
        admin_email: str,
        enabled: bool = True,
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.admin_email = admin_email
        self.enabled = enabled
        
    async def send_healing_report(self, report: HealingReport) -> bool:
        """
        Send a complete healing report to admin.
        
        Args:
            report: The healing report to send
            
        Returns:
            True if email sent successfully
        """
        if not self.enabled:
            logger.info("Email notifications disabled, skipping...")
            return True
        
        if not self.sender_email or not self.sender_password:
            logger.warning("Email credentials not configured, skipping notification")
            return False
        
        try:
            subject = self._create_subject(report)
            html_content = self._create_html_report(report)
            text_content = self._create_text_report(report)
            
            await self._send_email(subject, html_content, text_content)
            logger.info(f"✓ Healing report sent to {self.admin_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def _create_subject(self, report: HealingReport) -> str:
        """Create email subject based on report status"""
        status_emoji = "✅" if report.status == "success" else "🚨"
        severity = report.error_info.severity.value.upper()
        
        return f"{status_emoji} [{severity}] Self-Healing Report: {report.error_info.error_type}"
    
    def _create_html_report(self, report: HealingReport) -> str:
        """Create HTML formatted report"""
        status_color = "#28a745" if report.status == "success" else "#dc3545"
        severity_colors = {
            "low": "#17a2b8",
            "medium": "#ffc107",
            "high": "#fd7e14",
            "critical": "#dc3545",
        }
        severity_color = severity_colors.get(report.error_info.severity.value, "#6c757d")
        
        # Build test results table
        test_rows = ""
        for tr in report.test_results:
            result_color = "#28a745" if tr.passed else "#dc3545"
            test_rows += f"""
            <tr>
                <td>{tr.fix_id[:8]}...</td>
                <td style="color: {result_color};">{'✓ PASSED' if tr.passed else '✗ FAILED'}</td>
                <td>{tr.pass_rate:.1f}%</td>
                <td>{tr.execution_time:.2f}s</td>
            </tr>
            """
        
        # Build fix details
        fix_details = ""
        if report.final_fix:
            fix_details = f"""
            <h3>✅ Applied Fix</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td><strong>File:</strong></td><td>{report.final_fix.target_file}</td></tr>
                <tr><td><strong>Confidence:</strong></td><td>{report.final_fix.confidence_score:.2%}</td></tr>
                <tr><td><strong>Attempt:</strong></td><td>#{report.final_fix.attempt_number}</td></tr>
            </table>
            <h4>Explanation:</h4>
            <p style="background: #f8f9fa; padding: 10px; border-radius: 5px;">{report.final_fix.explanation}</p>
            """
        
        # Git information
        git_info = ""
        if report.git_branch:
            git_info = f"""
            <h3>🔗 Git Information</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td><strong>Branch:</strong></td><td><code>{report.git_branch}</code></td></tr>
                <tr><td><strong>Commit:</strong></td><td><code>{report.git_commit or 'N/A'}</code></td></tr>
            </table>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; }}
                .content {{ background: #fff; padding: 30px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 10px 10px; }}
                .status {{ display: inline-block; padding: 5px 15px; border-radius: 20px; color: white; font-weight: bold; background: {status_color}; }}
                .severity {{ display: inline-block; padding: 5px 15px; border-radius: 20px; color: white; font-weight: bold; background: {severity_color}; }}
                table {{ margin: 15px 0; }}
                td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
                code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
                pre {{ background: #2d2d2d; color: #f8f8f2; padding: 15px; border-radius: 5px; overflow-x: auto; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🤖 Self-Healing Report</h1>
                    <p>Report ID: {report.report_id}</p>
                    <p>{report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                <div class="content">
                    <p>
                        <span class="status">{report.status.upper()}</span>
                        <span class="severity">{report.error_info.severity.value.upper()}</span>
                    </p>
                    
                    <h3>🔴 Error Details</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr><td><strong>Type:</strong></td><td>{report.error_info.error_type}</td></tr>
                        <tr><td><strong>Message:</strong></td><td>{report.error_info.message}</td></tr>
                        <tr><td><strong>File:</strong></td><td><code>{report.error_info.source_file}</code></td></tr>
                        <tr><td><strong>Line:</strong></td><td>{report.error_info.line_number}</td></tr>
                    </table>
                    
                    <h4>Root Cause Analysis:</h4>
                    <p style="background: #fff3cd; padding: 10px; border-radius: 5px; border-left: 4px solid #ffc107;">
                        {report.error_info.root_cause_analysis}
                    </p>
                    
                    <h4>Stack Trace:</h4>
                    <pre>{report.error_info.stack_trace[:1000]}{'...' if len(report.error_info.stack_trace) > 1000 else ''}</pre>
                    
                    <h3>🧪 Test Results</h3>
                    <p>Total Attempts: {report.total_attempts}</p>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 10px; text-align: left;">Fix ID</th>
                            <th style="padding: 10px; text-align: left;">Status</th>
                            <th style="padding: 10px; text-align: left;">Pass Rate</th>
                            <th style="padding: 10px; text-align: left;">Time</th>
                        </tr>
                        {test_rows}
                    </table>
                    
                    {fix_details}
                    {git_info}
                    
                </div>
                <div class="footer">
                    <p>This report was automatically generated by the Self-Healing Software System</p>
                    <p>© {datetime.now().year} Self-Healing System</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _create_text_report(self, report: HealingReport) -> str:
        """Create plain text report as fallback"""
        return report.summary()
    
    async def _send_email(
        self, 
        subject: str, 
        html_content: str, 
        text_content: str
    ):
        """Send email using SMTP with app password"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender_email
        msg["To"] = self.admin_email
        
        # Attach both plain text and HTML versions
        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Create secure connection and send
        context = ssl.create_default_context()
        
        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls(context=context)
            server.login(self.sender_email, self.sender_password)
            server.sendmail(self.sender_email, self.admin_email, msg.as_string())
    
    async def send_quick_alert(
        self, 
        error_type: str, 
        message: str, 
        severity: str
    ) -> bool:
        """Send a quick alert for urgent issues"""
        if not self.enabled:
            return True
        
        subject = f"🚨 ALERT: {error_type} - {severity.upper()}"
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #dc3545;">⚠️ Urgent Alert</h2>
            <p><strong>Error Type:</strong> {error_type}</p>
            <p><strong>Severity:</strong> {severity}</p>
            <p><strong>Message:</strong> {message}</p>
            <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body>
        </html>
        """
        
        text = f"ALERT: {error_type}\nSeverity: {severity}\nMessage: {message}"
        
        try:
            await self._send_email(subject, html, text)
            return True
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
            return False
