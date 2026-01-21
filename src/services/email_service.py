"""
Email Service for the Self-Healing Software System v2.0

Sends rich HTML emails with:
- Error analysis results
- Fix proposals
- Interactive AST visualization (SVG)
- Code review results
"""

import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List
from datetime import datetime
import html

from config import get_config
from utils.models import (
    AnalysisEmail, CodeReviewEmail, RootCauseAnalysis, FixProposal,
    CodeReviewResult, ASTVisualization, DetectedError
)
from utils.logger import setup_colored_logger


logger = setup_colored_logger("email_service")


class EmailService:
    """
    Service for sending rich HTML emails.
    
    Features:
    - Analysis result emails with AST visualization
    - Code review result emails
    - Fix proposal summaries
    - Interactive elements in emails
    """
    
    def __init__(self, config = None):
        """
        Initialize the email service.
        
        Args:
            config: Email configuration (uses global config if not provided)
        """
        self.config = config or get_config().email
        
    async def send_analysis_email(
        self,
        to_email: str,
        analysis: RootCauseAnalysis,
        proposals: List[FixProposal],
        ast_viz: Optional[ASTVisualization] = None,
    ) -> bool:
        """
        Send an error analysis email.
        
        Args:
            to_email: Recipient email address
            analysis: Root cause analysis
            proposals: List of fix proposals
            ast_viz: Optional AST visualization
            
        Returns:
            True if email was sent successfully
        """
        if not self.config.enable_notifications:
            logger.info("Email notifications disabled")
            return False
        
        # Build error summary from analysis
        error = analysis.error if hasattr(analysis, 'error') and analysis.error else None
        error_type = error.error_type if error else "Unknown Error"
        error_summary = f"{error_type}: {analysis.root_cause[:200] if analysis.root_cause else 'Unknown'}"
        
        email_data = AnalysisEmail(
            recipient=to_email,
            subject=f"[Self-Healer] Error Analysis: {error_type}",
            error_summary=error_summary,
            root_cause_analysis=analysis,
            fix_proposals=proposals or [],
            ast_visualization=ast_viz,
        )
        
        html_content = self._build_analysis_html(email_data)
        
        return await self._send_email(
            to=to_email,
            subject=email_data.subject,
            html_content=html_content,
        )
    
    async def send_code_review_email(
        self,
        to_email: str,
        review: CodeReviewResult,
    ) -> bool:
        """
        Send a code review result email.
        
        Args:
            to_email: Recipient email address
            review: Code review result
            
        Returns:
            True if email was sent successfully
        """
        if not self.config.enable_notifications:
            logger.info("Email notifications disabled")
            return False
        
        email_data = CodeReviewEmail(
            to=to_email,
            review=review,
        )
        
        html_content = self._build_review_html(email_data)
        
        return await self._send_email(
            to=to_email,
            subject=f"[Self-Healer] Code Review: PR #{review.pr_info.pr_number}",
            html_content=html_content,
        )
    
    def _build_analysis_html(self, email: AnalysisEmail) -> str:
        """Build HTML content for analysis email."""
        
        analysis = email.root_cause_analysis
        error = analysis.error if analysis and hasattr(analysis, 'error') and analysis.error else None
        
        # Escape HTML in user-provided content
        error_msg = html.escape(error.message[:500] if error else email.error_summary[:500])
        root_cause = html.escape(analysis.root_cause if analysis else "Unknown")
        
        # Severity color
        severity_colors = {
            "critical": "#dc3545",
            "high": "#fd7e14",
            "medium": "#ffc107",
            "low": "#28a745",
        }
        severity_color = severity_colors.get(analysis.severity if analysis else "medium", "#6c757d")
        
        # Build proposals HTML
        proposals_html = ""
        for i, proposal in enumerate(email.fix_proposals, 1):
            proposals_html += f"""
            <div style="background: #f8f9fa; border-left: 4px solid #007bff; padding: 15px; margin: 10px 0;">
                <h4 style="margin: 0 0 10px 0; color: #007bff;">Proposal {i}</h4>
                <p style="margin: 5px 0;"><strong>File:</strong> {html.escape(proposal.target_file or 'Unknown')}</p>
                <p style="margin: 5px 0;"><strong>Confidence:</strong> {proposal.confidence:.0%}</p>
                <p style="margin: 10px 0;">{html.escape(proposal.explanation)}</p>
                {f'<pre style="background: #2d2d2d; color: #f8f8f2; padding: 10px; overflow-x: auto;">{html.escape(proposal.suggested_code)}</pre>' if proposal.suggested_code else ''}
                {'<p style="color: #856404;"><strong>⚠️ Potential Side Effects:</strong> ' + ', '.join(html.escape(e) for e in proposal.side_effects) + '</p>' if proposal.side_effects else ''}
            </div>
            """
        
        # AST visualization
        ast_html = ""
        if email.ast_visualization and email.ast_visualization.svg_content:
            ast_html = f"""
            <div style="margin: 20px 0;">
                <h3 style="color: #495057;">📊 AST Visualization</h3>
                <p style="color: #6c757d; font-size: 0.9em;">Click on nodes to expand/collapse. Error location is highlighted in red.</p>
                <div style="background: white; border: 1px solid #dee2e6; padding: 10px; overflow-x: auto;">
                    {email.ast_visualization.svg_content}
                </div>
            </div>
            """
        
        # Get values with fallbacks
        error_type = error.error_type if error else "Unknown Error"
        source_file = error.source_file if error else "Unknown"
        line_number = error.line_number if error else "?"
        timestamp = error.timestamp if error else email.timestamp
        stack_trace = error.stack_trace if error and error.stack_trace else None
        severity = analysis.severity if analysis else "medium"
        confidence = analysis.confidence if analysis else 0.5
        error_category = analysis.error_category if analysis else "unknown"
        affected_components = analysis.affected_components if analysis else []
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0; }}
        .content {{ background: white; padding: 30px; border: 1px solid #dee2e6; border-top: none; border-radius: 0 0 8px 8px; }}
        .severity-badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: 600; }}
        .stack-trace {{ background: #2d2d2d; color: #f8f8f2; padding: 15px; border-radius: 4px; overflow-x: auto; font-family: 'Monaco', 'Menlo', monospace; font-size: 0.85em; }}
        .section {{ margin: 25px 0; }}
        .section-title {{ color: #495057; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0;">🔧 Error Analysis Report</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Self-Healing Software System</p>
        </div>
        
        <div class="content">
            <!-- Error Summary -->
            <div class="section">
                <h2 class="section-title">🚨 Error Summary</h2>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #6c757d; width: 120px;">Type</td>
                        <td style="padding: 8px 0; font-weight: 600;">{html.escape(error_type)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #6c757d;">Severity</td>
                        <td style="padding: 8px 0;">
                            <span class="severity-badge" style="background: {severity_color}; color: white;">
                                {severity.upper()}
                            </span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #6c757d;">Location</td>
                        <td style="padding: 8px 0;">{html.escape(str(source_file))}:{line_number}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #6c757d;">Timestamp</td>
                        <td style="padding: 8px 0;">{timestamp.strftime('%Y-%m-%d %H:%M:%S UTC') if hasattr(timestamp, 'strftime') else str(timestamp)}</td>
                    </tr>
                </table>
                
                <div style="background: #f8f9fa; padding: 15px; border-radius: 4px; margin-top: 15px;">
                    <strong>Error Message:</strong><br>
                    <code style="color: #dc3545;">{error_msg}</code>
                </div>
            </div>
            
            {f'''
            <div class="section">
                <h3 class="section-title">📋 Stack Trace</h3>
                <pre class="stack-trace">{html.escape(stack_trace[:2000])}</pre>
            </div>
            ''' if stack_trace else ''}
            
            <!-- Root Cause Analysis -->
            <div class="section">
                <h2 class="section-title">🔍 Root Cause Analysis</h2>
                <div style="background: #e7f3ff; border-left: 4px solid #007bff; padding: 15px;">
                    <p style="margin: 0;">{root_cause}</p>
                </div>
                <p style="color: #6c757d; font-size: 0.9em; margin-top: 10px;">
                    Analysis confidence: {confidence:.0%} | 
                    Category: {html.escape(error_category)}
                </p>
                {f'<p><strong>Affected Components:</strong> {", ".join(html.escape(c) for c in affected_components)}</p>' if affected_components else ''}
            </div>
            
            <!-- Fix Proposals -->
            <div class="section">
                <h2 class="section-title">💡 Fix Proposals</h2>
                {proposals_html if proposals_html else '<p style="color: #6c757d;">No fix proposals generated.</p>'}
            </div>
            
            {ast_html}
            
            <!-- Footer -->
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; color: #6c757d; font-size: 0.85em;">
                <p>This is an automated analysis. Please review the proposals carefully before applying any changes.</p>
                <p>Generated by Self-Healing Software System v2.0 at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            </div>
        </div>
    </div>
</body>
</html>
"""
    
    def _build_review_html(self, email: CodeReviewEmail) -> str:
        """Build HTML content for code review email."""
        
        review = email.review
        pr = review.pr_info
        
        # Assessment color
        assessment_colors = {
            "approve": "#28a745",
            "request_changes": "#dc3545",
            "comment": "#ffc107",
        }
        assessment_color = assessment_colors.get(review.overall_assessment, "#6c757d")
        
        assessment_icons = {
            "approve": "✅",
            "request_changes": "❌",
            "comment": "💬",
        }
        assessment_icon = assessment_icons.get(review.overall_assessment, "📝")
        
        # Build comments HTML
        comments_html = ""
        for comment in review.comments:
            severity_colors = {
                "critical": "#dc3545",
                "warning": "#fd7e14",
                "suggestion": "#007bff",
                "nitpick": "#6c757d",
            }
            comment_color = severity_colors.get(comment.severity, "#6c757d")
            
            comments_html += f"""
            <div style="border-left: 4px solid {comment_color}; padding: 10px 15px; margin: 10px 0; background: #f8f9fa;">
                <p style="margin: 0 0 5px 0; color: #6c757d; font-size: 0.85em;">
                    {html.escape(comment.file_path)}:{comment.line_number or '?'} • 
                    <span style="color: {comment_color}; font-weight: 600;">{comment.severity.upper()}</span> • 
                    {html.escape(comment.category)}
                </p>
                <p style="margin: 5px 0;">{html.escape(comment.comment)}</p>
                {f'<pre style="background: #2d2d2d; color: #f8f8f2; padding: 10px; font-size: 0.85em; margin-top: 10px;">{html.escape(comment.suggestion)}</pre>' if comment.suggestion else ''}
            </div>
            """
        
        # Highlights
        highlights_html = ""
        if review.highlights:
            highlights_html = "<ul>" + "".join(f"<li>{html.escape(h)}</li>" for h in review.highlights) + "</ul>"
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0; }}
        .content {{ background: white; padding: 30px; border: 1px solid #dee2e6; border-top: none; border-radius: 0 0 8px 8px; }}
        .section {{ margin: 25px 0; }}
        .section-title {{ color: #495057; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0;">📝 Code Review Report</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">PR #{pr.pr_number}: {html.escape(pr.title or 'Untitled')}</p>
        </div>
        
        <div class="content">
            <!-- Overall Assessment -->
            <div style="text-align: center; padding: 20px; background: #f8f9fa; border-radius: 8px; margin-bottom: 20px;">
                <div style="font-size: 48px;">{assessment_icon}</div>
                <div style="font-size: 1.2em; font-weight: 600; color: {assessment_color}; text-transform: uppercase;">
                    {review.overall_assessment.replace('_', ' ')}
                </div>
            </div>
            
            <!-- Summary -->
            <div class="section">
                <h2 class="section-title">📋 Summary</h2>
                <p>{html.escape(review.summary)}</p>
            </div>
            
            <!-- PR Details -->
            <div class="section">
                <h3 class="section-title">🔀 Pull Request Details</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; color: #6c757d; width: 120px;">Base Branch</td>
                        <td style="padding: 8px 0;">{html.escape(pr.base_branch)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #6c757d;">Head Branch</td>
                        <td style="padding: 8px 0;">{html.escape(pr.head_branch)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #6c757d;">Reviewed At</td>
                        <td style="padding: 8px 0;">{review.reviewed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
                    </tr>
                </table>
            </div>
            
            <!-- Comments -->
            <div class="section">
                <h2 class="section-title">💬 Review Comments ({len(review.comments)})</h2>
                {comments_html if comments_html else '<p style="color: #6c757d;">No comments.</p>'}
            </div>
            
            {f'''
            <div class="section">
                <h3 class="section-title">✨ Highlights</h3>
                {highlights_html}
            </div>
            ''' if highlights_html else ''}
            
            <!-- Footer -->
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; color: #6c757d; font-size: 0.85em;">
                <p>This is an automated code review. Human judgment should be applied before merging.</p>
                <p>Generated by Self-Healing Software System v2.0</p>
            </div>
        </div>
    </div>
</body>
</html>
"""
    
    async def _send_email(
        self, to: str, subject: str, html_content: str
    ) -> bool:
        """Send an email using SMTP."""
        
        if not self.config.sender_email or not self.config.sender_password:
            logger.error("Email sender credentials not configured")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.sender_email
            msg["To"] = to
            
            # Attach HTML content
            html_part = MIMEText(html_content, "html")
            msg.attach(html_part)
            
            # Send email in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._send_smtp,
                msg,
            )
            
            logger.info(f"✓ Email sent to {to}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def _send_smtp(self, msg: MIMEMultipart):
        """Send email via SMTP (blocking call)."""
        
        with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
            server.starttls()
            server.login(self.config.sender_email, self.config.sender_password)
            server.send_message(msg)


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create the email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
