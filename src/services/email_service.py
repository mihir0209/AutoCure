"""
Email Service for the Self-Healing Software System v2.0

Sends rich HTML emails with:
- Error analysis results with AST trace (not stack trace)
- Fix proposals with confidence validation
- Interactive AST tree visualization (HTML)
- Code review results
- High/Low confidence templates
"""

import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List, Dict, Any
from datetime import datetime
import html

from config import get_config
from utils.models import (
    AnalysisEmail, CodeReviewEmail, RootCauseAnalysis, FixProposal,
    CodeReviewResult, ASTVisualization, DetectedError, ASTNode
)
from utils.logger import setup_colored_logger

# Import AST trace and validation types
try:
    from services.ast_trace_service import ASTTraceContext, Reference, ProjectRequirements
    from services.confidence_validator import ValidationResult, ValidationIteration
except ImportError:
    # Graceful fallback if services not available
    ASTTraceContext = None
    ValidationResult = None
    Reference = None
    ProjectRequirements = None
    ValidationIteration = None


logger = setup_colored_logger("email_service")


# ==========================================
# AST Tree HTML Builder
# ==========================================

class ASTTreeHTMLBuilder:
    """
    Builds HTML representations of AST trees for email visualization.
    
    Features:
    - Interactive collapsible tree view
    - Error path highlighting
    - Node type coloring
    """
    
    # Node type colors
    NODE_COLORS = {
        "module": "#9C27B0",
        "class": "#2196F3",
        "function": "#4CAF50",
        "method": "#8BC34A",
        "async_function": "#00BCD4",
        "import": "#FF9800",
        "variable": "#795548",
        "assignment": "#607D8B",
        "call": "#E91E63",
        "if": "#673AB7",
        "for": "#3F51B5",
        "while": "#009688",
        "try": "#FFC107",
        "except": "#FF5722",
        "return": "#CDDC39",
        "default": "#9E9E9E"
    }
    
    @classmethod
    def build_ast_tree_html(
        cls,
        root: 'ASTNode',
        error_line: int = 0,
        error_path: List['ASTNode'] = None,
        max_depth: int = 5
    ) -> str:
        """
        Build an interactive HTML tree representation of an AST.
        
        Args:
            root: Root AST node
            error_line: Line number of the error (for highlighting)
            error_path: Path of nodes to the error location
            max_depth: Maximum depth to render
            
        Returns:
            HTML string for the tree visualization
        """
        if not root:
            return '<p style="color: #6c757d;">No AST available</p>'
        
        error_path_ids = set()
        if error_path:
            for node in error_path:
                error_path_ids.add(id(node))
        
        def render_node(node: 'ASTNode', depth: int = 0) -> str:
            if depth > max_depth:
                return '<span style="color: #6c757d;">...</span>'
            
            is_error_path = id(node) in error_path_ids
            contains_error = node.start_line <= error_line <= node.end_line if error_line else False
            
            # Determine node styling
            node_type = node.node_type.lower() if node.node_type else "default"
            color = cls.NODE_COLORS.get(node_type, cls.NODE_COLORS["default"])
            
            # Highlight error path
            bg_color = ""
            border = ""
            if is_error_path:
                bg_color = "background: rgba(255, 0, 0, 0.1);"
                border = "border-left: 3px solid #dc3545;"
            elif contains_error:
                bg_color = "background: rgba(255, 193, 7, 0.1);"
            
            # Format node name
            name = html.escape(node.name or node.node_type or "?")
            
            # Build line info
            line_info = f":{node.start_line}"
            if node.end_line != node.start_line:
                line_info += f"-{node.end_line}"
            
            # Build children HTML
            children_html = ""
            if node.children and depth < max_depth:
                child_items = []
                for child in node.children[:20]:  # Limit children
                    child_items.append(render_node(child, depth + 1))
                
                if len(node.children) > 20:
                    child_items.append(f'<li style="color: #6c757d;">... {len(node.children) - 20} more</li>')
                
                children_html = f'''
                <ul style="margin: 2px 0 2px 15px; padding-left: 10px; border-left: 1px dashed #dee2e6; list-style: none;">
                    {"".join(f'<li style="margin: 2px 0;">{item}</li>' for item in child_items)}
                </ul>
                '''
            
            return f'''
            <div style="padding: 3px 5px; {bg_color} {border}">
                <span style="color: {color}; font-weight: 600;">●</span>
                <span style="color: #333;">{name}</span>
                <span style="color: #6c757d; font-size: 0.85em;">({node.node_type})</span>
                <span style="color: #007bff; font-size: 0.8em;">{line_info}</span>
                {children_html}
            </div>
            '''
        
        return f'''
        <div style="font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 0.85em; line-height: 1.4;">
            {render_node(root)}
        </div>
        '''
    
    @classmethod
    def build_error_path_html(cls, error_path: List['ASTNode']) -> str:
        """
        Build a visual representation of the path from root to error.
        
        Args:
            error_path: List of AST nodes from root to error location
            
        Returns:
            HTML string showing the error path
        """
        if not error_path:
            return '<p style="color: #6c757d;">No error path available</p>'
        
        path_items = []
        for i, node in enumerate(error_path):
            is_last = i == len(error_path) - 1
            node_type = node.node_type.lower() if node.node_type else "default"
            color = cls.NODE_COLORS.get(node_type, cls.NODE_COLORS["default"])
            
            name = html.escape(node.name or node.node_type or "?")
            line = f"L{node.start_line}"
            
            arrow = "" if is_last else " → "
            style = "font-weight: 700; color: #dc3545;" if is_last else ""
            
            path_items.append(
                f'<span style="background: {color}22; padding: 2px 6px; border-radius: 3px; {style}">'
                f'{name} <small style="opacity: 0.7;">({line})</small>'
                f'</span>{arrow}'
            )
        
        return f'''
        <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 4px; font-size: 0.9em;">
            {"".join(path_items)}
        </div>
        '''


class EmailService:
    """
    Service for sending rich HTML emails.
    
    Features:
    - Analysis result emails with AST trace visualization
    - High/Low confidence templates based on validation
    - Code review result emails
    - Fix proposal summaries
    - Interactive elements in emails
    """
    
    # Confidence threshold for high vs low confidence templates
    CONFIDENCE_THRESHOLD = 75.0
    
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
        ast_trace: Optional['ASTTraceContext'] = None,
        validation_result: Optional['ValidationResult'] = None,
    ) -> bool:
        """
        Send an error analysis email with AST trace and confidence validation.
        
        Args:
            to_email: Recipient email address
            analysis: Root cause analysis
            proposals: List of fix proposals
            ast_viz: Optional AST visualization (legacy SVG)
            ast_trace: AST trace context with error path and references
            validation_result: Multi-iteration validation result with confidence
            
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
        
        # Determine confidence level and template type
        confidence_met = True
        confidence_score = 100.0
        
        if validation_result:
            confidence_met = validation_result.confidence_met
            confidence_score = validation_result.confidence_score
        elif hasattr(analysis, 'confidence'):
            confidence_score = analysis.confidence * 100
            confidence_met = confidence_score >= self.CONFIDENCE_THRESHOLD
        
        email_data = AnalysisEmail(
            recipient=to_email,
            subject=f"[Self-Healer] {'⚠️ ' if not confidence_met else ''}Error Analysis: {error_type}",
            error_summary=error_summary,
            root_cause_analysis=analysis,
            fix_proposals=proposals or [],
            ast_visualization=ast_viz,
        )
        
        # Build HTML based on confidence level
        if confidence_met:
            html_content = self._build_high_confidence_html(
                email_data, ast_trace, validation_result
            )
        else:
            html_content = self._build_low_confidence_html(
                email_data, ast_trace, validation_result
            )
        
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
    
    # ==========================================
    # Common Email Styles
    # ==========================================
    
    def _get_common_styles(self) -> str:
        """Get common CSS styles for emails."""
        return """
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 900px; margin: 0 auto; padding: 20px; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0; }
        .header-warning { background: linear-gradient(135deg, #fd7e14 0%, #dc3545 100%); }
        .content { background: white; padding: 30px; border: 1px solid #dee2e6; border-top: none; border-radius: 0 0 8px 8px; }
        .severity-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: 600; }
        .confidence-badge { display: inline-block; padding: 6px 14px; border-radius: 20px; font-size: 0.9em; font-weight: 600; }
        .section { margin: 25px 0; }
        .section-title { color: #495057; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }
        .ast-trace { background: #f8f9fa; padding: 15px; border-radius: 4px; font-family: 'Monaco', 'Menlo', monospace; font-size: 0.85em; }
        .code-context { background: #2d2d2d; color: #f8f8f2; padding: 15px; border-radius: 4px; overflow-x: auto; font-family: 'Monaco', 'Menlo', monospace; font-size: 0.85em; white-space: pre; }
        .error-line { background: rgba(220, 53, 69, 0.3); display: block; }
        .progress-bar { background: #e9ecef; border-radius: 10px; overflow: hidden; height: 20px; }
        .progress-fill { height: 100%; border-radius: 10px; transition: width 0.3s; }
        .iteration-card { background: #f8f9fa; border-radius: 4px; padding: 10px; margin: 5px 0; }
        .possible-cause { background: #fff3cd; border-left: 4px solid #ffc107; padding: 10px 15px; margin: 8px 0; }
        .reference-item { background: #e7f3ff; border-left: 3px solid #007bff; padding: 8px 12px; margin: 5px 0; font-size: 0.9em; }
        """

    # ==========================================
    # High Confidence Template
    # ==========================================
    
    def _build_high_confidence_html(
        self,
        email: AnalysisEmail,
        ast_trace: Optional['ASTTraceContext'] = None,
        validation_result: Optional['ValidationResult'] = None
    ) -> str:
        """
        Build HTML content for high-confidence analysis email.
        
        Shows fix proposals prominently since we're confident in the analysis.
        """
        analysis = email.root_cause_analysis
        error = analysis.error if analysis and hasattr(analysis, 'error') and analysis.error else None
        
        # Get values with fallbacks
        error_type = error.error_type if error else "Unknown Error"
        error_msg = html.escape(error.message[:500] if error else email.error_summary[:500])
        source_file = error.source_file if error else "Unknown"
        line_number = error.line_number if error else "?"
        timestamp = error.timestamp if error else email.timestamp
        severity = analysis.severity if analysis else "medium"
        root_cause = html.escape(analysis.root_cause if analysis else "Unknown")
        error_category = analysis.error_category if analysis else "unknown"
        affected_components = analysis.affected_components if analysis else []
        
        # Severity color
        severity_colors = {
            "critical": "#dc3545", "high": "#fd7e14", 
            "medium": "#ffc107", "low": "#28a745",
        }
        severity_color = severity_colors.get(severity, "#6c757d")
        
        # Confidence info
        confidence_score = validation_result.confidence_score if validation_result else (analysis.confidence * 100 if analysis else 50)
        
        # Build sections
        validation_html = self._build_validation_html(validation_result) if validation_result else ""
        ast_trace_html = self._build_ast_trace_html(ast_trace, error_line=line_number if isinstance(line_number, int) else 0) if ast_trace else ""
        proposals_html = self._build_proposals_html(email.fix_proposals)
        dependencies_html = self._build_dependencies_html(ast_trace) if ast_trace and ast_trace.requirements else ""
        #         <div class="header">
        #     <h1 style="margin: 0;">✅ Error Analysis Report</h1>
        #     <p style="margin: 10px 0 0 0; opacity: 0.9;">High Confidence Analysis - Fix Suggestions Ready</p>
        # </div>
        
        # <div class="content">
        #     <!-- Confidence Banner -->
        #     <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 4px; padding: 15px; margin-bottom: 20px;">
        #         <div style="display: flex; align-items: center; gap: 10px;">
        #             <span style="font-size: 1.5em;">✅</span>
        #             <div>
        #                 <strong style="color: #155724;">High Confidence Analysis ({confidence_score:.0f}%)</strong>
        #                 <p style="margin: 5px 0 0 0; color: #155724; font-size: 0.9em;">
        #                     Multiple validation iterations confirmed the root cause. Fix proposals are provided below.
        #                 </p>
        #             </div>
        #         </div>
        #     </div>
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{self._get_common_styles()}</style>
</head>
<body>
    <div class="container">

            
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
                            <span class="severity-badge" style="background: {severity_color}; color: white;">{severity.upper()}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #6c757d;">Location</td>
                        <td style="padding: 8px 0;"><code>{html.escape(str(source_file))}:{line_number}</code></td>
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
            
            {validation_html}
            
            {ast_trace_html}
            
            <!-- Root Cause Analysis -->
            <div class="section">
                <h2 class="section-title">🔍 Root Cause Analysis</h2>
                <div style="background: #e7f3ff; border-left: 4px solid #007bff; padding: 15px;">
                    <p style="margin: 0;">{root_cause}</p>
                </div>
                <p style="color: #6c757d; font-size: 0.9em; margin-top: 10px;">
                    Category: {html.escape(error_category)}
                </p>
                {f'<p><strong>Affected Components:</strong> {", ".join(html.escape(c) for c in affected_components)}</p>' if affected_components else ''}
            </div>
            
            <!-- Fix Proposals -->
            <div class="section">
                <h2 class="section-title">💡 Fix Proposals</h2>
                {proposals_html if proposals_html else '<p style="color: #6c757d;">No fix proposals generated.</p>'}
            </div>
            
            {dependencies_html}
            
            <!-- Footer -->
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; color: #6c757d; font-size: 0.85em;">
                <p>This is an automated analysis with high confidence. Please review the proposals carefully before applying any changes.</p>
                <p>Generated by Self-Healing Software System v2.0 at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

    # ==========================================
    # Low Confidence Template
    # ==========================================
    
    def _build_low_confidence_html(
        self,
        email: AnalysisEmail,
        ast_trace: Optional['ASTTraceContext'] = None,
        validation_result: Optional['ValidationResult'] = None
    ) -> str:
        """
        Build HTML content for low-confidence analysis email.
        
        Shows possible causes instead of fix proposals since we're not confident.
        """
        analysis = email.root_cause_analysis
        error = analysis.error if analysis and hasattr(analysis, 'error') and analysis.error else None
        
        # Get values with fallbacks
        error_type = error.error_type if error else "Unknown Error"
        error_msg = html.escape(error.message[:500] if error else email.error_summary[:500])
        source_file = error.source_file if error else "Unknown"
        line_number = error.line_number if error else "?"
        timestamp = error.timestamp if error else email.timestamp
        severity = analysis.severity if analysis else "medium"
        error_category = analysis.error_category if analysis else "unknown"
        
        # Severity color
        severity_colors = {
            "critical": "#dc3545", "high": "#fd7e14", 
            "medium": "#ffc107", "low": "#28a745",
        }
        severity_color = severity_colors.get(severity, "#6c757d")
        
        # Confidence info
        confidence_score = validation_result.confidence_score if validation_result else (analysis.confidence * 100 if analysis else 50)
        
        # Build sections
        validation_html = self._build_validation_html(validation_result) if validation_result else ""
        ast_trace_html = self._build_ast_trace_html(ast_trace, error_line=line_number if isinstance(line_number, int) else 0) if ast_trace else ""
        possible_causes_html = self._build_possible_causes_html(validation_result) if validation_result else ""
        dependencies_html = self._build_dependencies_html(ast_trace) if ast_trace and ast_trace.requirements else ""
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{self._get_common_styles()}</style>
</head>
<body>
    <div class="container">
        <div class="header header-warning">
            <h1 style="margin: 0;">⚠️ Error Analysis Report</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Low Confidence - Manual Review Recommended</p>
        </div>
        
        <div class="content">
            <!-- Warning Banner -->
            <div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 15px; margin-bottom: 20px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 1.5em;">⚠️</span>
                    <div>
                        <strong style="color: #856404;">Low Confidence Analysis ({confidence_score:.0f}%)</strong>
                        <p style="margin: 5px 0 0 0; color: #856404; font-size: 0.9em;">
                            Validation iterations showed inconsistent results. Possible causes are listed below instead of fix proposals.
                        </p>
                    </div>
                </div>
            </div>
            
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
                            <span class="severity-badge" style="background: {severity_color}; color: white;">{severity.upper()}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #6c757d;">Location</td>
                        <td style="padding: 8px 0;"><code>{html.escape(str(source_file))}:{line_number}</code></td>
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
            
            {validation_html}
            
            {ast_trace_html}
            
            <!-- Possible Causes -->
            <div class="section">
                <h2 class="section-title">🤔 Possible Causes</h2>
                <p style="color: #6c757d; font-size: 0.9em; margin-bottom: 15px;">
                    Since confidence is below 75%, here are potential causes that should be investigated:
                </p>
                {possible_causes_html if possible_causes_html else '<p style="color: #6c757d;">No specific causes identified.</p>'}
            </div>
            
            {dependencies_html}
            
            <!-- Footer -->
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; color: #6c757d; font-size: 0.85em;">
                <p><strong>⚠️ Manual investigation is recommended</strong> due to low confidence in the analysis.</p>
                <p>Generated by Self-Healing Software System v2.0 at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

    # ==========================================
    # Helper Methods for Building Sections
    # ==========================================
    
    def _build_validation_html(self, validation_result: Optional['ValidationResult']) -> str:
        """Build HTML for validation/confidence section."""
        if not validation_result:
            return ""
        
        confidence_score = validation_result.confidence_score
        confidence_met = validation_result.confidence_met
        total_iterations = len(validation_result.iterations) + 1  # +1 for initial
        matching_iterations = validation_result.matching_iterations + 1  # +1 for initial match
        
        # Progress bar color
        if confidence_score >= 75:
            bar_color = "#28a745"
        elif confidence_score >= 50:
            bar_color = "#ffc107"
        else:
            bar_color = "#dc3545"
        
        # Build iteration details
        iteration_items = ""
        for iteration in validation_result.iterations[:5]:  # Limit to 5
            match_icon = "✅" if iteration.matches_initial else "❌"
            match_style = "color: #28a745;" if iteration.matches_initial else "color: #dc3545;"
            
            iteration_items += f"""
            <div class="iteration-card">
                <span style="{match_style} font-weight: 600;">{match_icon}</span>
                <strong>Iteration {iteration.iteration_number}</strong> - {html.escape(iteration.payload_variation)}
                {f'<br><small style="color: #6c757d;">{html.escape(iteration.notes[:100])}</small>' if iteration.notes else ''}
            </div>
            """
        
        return f"""
        <div class="section">
            <h2 class="section-title">📊 Confidence Validation</h2>
            
            <!-- Confidence Score -->
            <div style="margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                    <span>Confidence Score</span>
                    <strong style="color: {bar_color};">{confidence_score:.0f}%</strong>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {confidence_score}%; background: {bar_color};"></div>
                </div>
                <p style="color: #6c757d; font-size: 0.85em; margin-top: 5px;">
                    Threshold: 75% | {matching_iterations}/{total_iterations} iterations matched
                </p>
            </div>
            
            <!-- Iteration Details -->
            <details style="margin-top: 15px;">
                <summary style="cursor: pointer; color: #007bff; font-weight: 600;">View Iteration Details</summary>
                <div style="margin-top: 10px;">
                    {iteration_items if iteration_items else '<p style="color: #6c757d;">No iteration data available.</p>'}
                </div>
            </details>
        </div>
        """
    
    def _build_ast_trace_html(
        self, 
        ast_trace: Optional['ASTTraceContext'],
        error_line: int = 0
    ) -> str:
        """Build HTML for AST trace section."""
        if not ast_trace:
            return ""
        
        # Error path visualization
        error_path_html = ""
        if ast_trace.error_path:
            error_path_html = ASTTreeHTMLBuilder.build_error_path_html(ast_trace.error_path)
        
        # Code context
        code_context_html = ""
        if ast_trace.error_context_code:
            # Format code with error line highlighting
            lines = ast_trace.error_context_code.split('\n')
            formatted_lines = []
            for line in lines:
                if line.startswith(">>>"):
                    formatted_lines.append(f'<span class="error-line">{html.escape(line)}</span>')
                else:
                    formatted_lines.append(html.escape(line))
            code_context_html = '\n'.join(formatted_lines)
        
        # AST tree visualization
        ast_tree_html = ""
        if ast_trace.main_ast:
            ast_tree_html = ASTTreeHTMLBuilder.build_ast_tree_html(
                ast_trace.main_ast,
                error_line=error_line,
                error_path=ast_trace.error_path
            )
        
        # Cross-file references
        references_html = ""
        if ast_trace.references:
            ref_items = []
            for ref in ast_trace.references[:10]:  # Limit to 10
                resolved = f" → {html.escape(ref.resolved_path)}" if ref.resolved_path else ""
                ref_items.append(f"""
                <div class="reference-item">
                    <strong>{html.escape(ref.symbol_name)}</strong>
                    <span style="color: #6c757d;">({ref.ref_type})</span>
                    <br>
                    <small>from {html.escape(ref.from_file)}:{ref.line_number}{resolved}</small>
                </div>
                """)
            references_html = ''.join(ref_items)
        
        return f"""
        <div class="section">
            <h2 class="section-title">🌳 AST Trace</h2>
            
            <!-- Error Path -->
            {f'''
            <div style="margin-bottom: 20px;">
                <h4 style="color: #495057; margin-bottom: 10px;">Error Path</h4>
                <p style="color: #6c757d; font-size: 0.85em; margin-bottom: 8px;">Path from module root to error location:</p>
                {error_path_html}
            </div>
            ''' if error_path_html else ''}
            
            <!-- Code Context -->
            {f'''
            <div style="margin-bottom: 20px;">
                <h4 style="color: #495057; margin-bottom: 10px;">Code Context</h4>
                <pre class="code-context">{code_context_html}</pre>
            </div>
            ''' if code_context_html else ''}
            
            <!-- AST Tree -->
            {f'''
            <div style="margin-bottom: 20px;">
                <h4 style="color: #495057; margin-bottom: 10px;">AST Structure</h4>
                <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 15px; max-height: 400px; overflow: auto;">
                    {ast_tree_html}
                </div>
            </div>
            ''' if ast_tree_html else ''}
            
            <!-- Cross-file References -->
            {f'''
            <div style="margin-bottom: 20px;">
                <h4 style="color: #495057; margin-bottom: 10px;">Cross-File References</h4>
                {references_html}
            </div>
            ''' if references_html else ''}
        </div>
        """
    
    def _build_proposals_html(self, proposals: List[FixProposal]) -> str:
        """Build HTML for fix proposals section."""
        if not proposals:
            return '<p style="color: #6c757d;">No fix proposals generated.</p>'
        
        items = []
        for i, proposal in enumerate(proposals, 1):
            items.append(f"""
            <div style="background: #f8f9fa; border-left: 4px solid #007bff; padding: 15px; margin: 10px 0; border-radius: 0 4px 4px 0;">
                <h4 style="margin: 0 0 10px 0; color: #007bff;">Proposal {i}</h4>
                <p style="margin: 5px 0;"><strong>File:</strong> <code>{html.escape(proposal.target_file or 'Unknown')}</code></p>
                <p style="margin: 5px 0;"><strong>Confidence:</strong> {proposal.confidence:.0%}</p>
                <p style="margin: 10px 0;">{html.escape(proposal.explanation)}</p>
                {f'''
                <div style="margin-top: 10px;">
                    <strong>Suggested Code:</strong>
                    <pre style="background: #2d2d2d; color: #f8f8f2; padding: 10px; border-radius: 4px; overflow-x: auto; margin-top: 5px;">{html.escape(proposal.suggested_code)}</pre>
                </div>
                ''' if proposal.suggested_code else ''}
                {f'<p style="color: #856404; margin-top: 10px;"><strong>⚠️ Potential Side Effects:</strong> {", ".join(html.escape(e) for e in proposal.side_effects)}</p>' if proposal.side_effects else ''}
            </div>
            """)
        
        return ''.join(items)
    
    def _build_possible_causes_html(self, validation_result: Optional['ValidationResult']) -> str:
        """Build HTML for possible causes section (low confidence)."""
        if not validation_result:
            return ""
        
        items = []
        
        # Add possible causes
        for cause in validation_result.possible_causes[:5]:
            items.append(f"""
            <div class="possible-cause">
                <strong>🔸 Possible Cause:</strong>
                <p style="margin: 5px 0 0 0;">{html.escape(cause)}</p>
            </div>
            """)
        
        # Add divergent findings
        if validation_result.divergent_findings:
            items.append('<h4 style="color: #495057; margin-top: 20px;">Divergent Analysis Results:</h4>')
            for finding in validation_result.divergent_findings[:3]:
                items.append(f"""
                <div style="background: #f8d7da; border-left: 4px solid #dc3545; padding: 10px 15px; margin: 8px 0;">
                    <p style="margin: 0; font-size: 0.9em;">{html.escape(finding)}</p>
                </div>
                """)
        
        return ''.join(items) if items else '<p style="color: #6c757d;">No specific causes identified from validation.</p>'
    
    def _build_dependencies_html(self, ast_trace: Optional['ASTTraceContext']) -> str:
        """Build HTML for dependencies section."""
        if not ast_trace or not ast_trace.requirements:
            return ""
        
        reqs = ast_trace.requirements
        
        # Build dependency list
        dep_items = []
        all_deps = {**reqs.dependencies, **reqs.dev_dependencies}
        for name, version in list(all_deps.items())[:15]:  # Limit to 15
            is_dev = name in reqs.dev_dependencies
            badge = '<span style="background: #6c757d; color: white; padding: 1px 5px; border-radius: 3px; font-size: 0.7em; margin-left: 5px;">dev</span>' if is_dev else ''
            dep_items.append(f'<li><code>{html.escape(name)}</code>: {html.escape(version)}{badge}</li>')
        
        if len(all_deps) > 15:
            dep_items.append(f'<li style="color: #6c757d;">... and {len(all_deps) - 15} more</li>')
        
        return f"""
        <div class="section">
            <h2 class="section-title">📦 Project Dependencies</h2>
            <p style="color: #6c757d; font-size: 0.9em; margin-bottom: 10px;">
                From: <code>{html.escape(reqs.manifest_file)}</code> ({html.escape(reqs.language)})
            </p>
            <ul style="margin: 0; padding-left: 20px;">
                {''.join(dep_items)}
            </ul>
        </div>
        """
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
