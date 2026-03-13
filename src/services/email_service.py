"""
Email Service for the Self-Healing Software System v2.0

Sends rich HTML emails with:
- AST parser trace visualization (accordion-based, NOT stack traces)
- Interactive collapsible AST tree with <details>/<summary>
- Fix proposals with confidence validation
- Code context with error line highlighting
- Cross-file reference map
- Saves full HTML reports to disk for online viewing
"""

from __future__ import annotations

import asyncio
import os
import smtplib
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from pathlib import Path
import html as html_mod

import json as json_mod

from config import get_config
from utils.models import (
    AnalysisEmail, CodeReviewEmail, RootCauseAnalysis, FixProposal,
    CodeReviewResult, ASTVisualization, DetectedError, ASTNode,
)
from utils.logger import setup_colored_logger
from database.report_store import get_report_store, REPORTS_DIR

if TYPE_CHECKING:
    from services.ast_trace_service import ASTTraceContext, Reference, ProjectRequirements
    from services.confidence_validator import ValidationResult, ValidationIteration

# Import AST trace and validation types at runtime too (for isinstance etc.)
try:
    from services.ast_trace_service import ASTTraceContext, Reference, ProjectRequirements  # noqa: F811
    from services.confidence_validator import ValidationResult, ValidationIteration  # noqa: F811
except ImportError:
    pass

logger = setup_colored_logger("email_service")

# Report store is managed by database.report_store


# ════════════════════════════════════════════════════════════════
#  Colour palette (shared across all templates)
# ════════════════════════════════════════════════════════════════

_NODE_COLORS: Dict[str, str] = {
    "module": "#9C27B0", "program": "#9C27B0",
    "class": "#2196F3", "class_definition": "#2196F3",
    "function": "#4CAF50", "function_definition": "#4CAF50",
    "method": "#8BC34A", "async_function": "#00BCD4",
    "import": "#FF9800", "import_statement": "#FF9800",
    "import_from_statement": "#FF9800",
    "variable": "#795548", "assignment": "#607D8B",
    "call": "#E91E63", "call_expression": "#E91E63",
    "if": "#673AB7", "if_statement": "#673AB7",
    "for": "#3F51B5", "for_statement": "#3F51B5",
    "while": "#009688", "while_statement": "#009688",
    "try": "#FFC107", "try_statement": "#FFC107",
    "except": "#FF5722", "except_clause": "#FF5722",
    "return": "#CDDC39", "return_statement": "#CDDC39",
    "block": "#78909C", "expression_statement": "#90A4AE",
}
_DEFAULT_NODE_COLOR = "#9E9E9E"

_SEVERITY_COLORS: Dict[str, str] = {
    "critical": "#dc3545", "high": "#fd7e14",
    "medium": "#ffc107", "low": "#28a745",
}


def _esc(text: Any) -> str:
    """Shorthand HTML-escape."""
    return html_mod.escape(str(text)) if text else ""


def _node_color(node_type: str) -> str:
    return _NODE_COLORS.get((node_type or "").lower(), _DEFAULT_NODE_COLOR)


def _get_error(analysis: Optional[RootCauseAnalysis]):
    """Safely extract DetectedError from analysis."""
    if analysis and hasattr(analysis, 'error') and analysis.error:
        return analysis.error
    return None


def _ast_node_to_dict(node: ASTNode, max_depth: int = 12, depth: int = 0) -> Optional[dict]:
    """Recursively convert ASTNode to JSON-serializable dict for the interactive visualizer."""
    if node is None or depth > max_depth:
        return None
    d = {
        "type": node.node_type or "unknown",
        "name": node.name or "",
        "loc": {"start": {"line": node.start_line, "col": node.start_col},
                "end": {"line": node.end_line, "col": node.end_col}},
    }
    if node.code_snippet:
        d["snippet"] = node.code_snippet.split("\n")[0][:120]
    if node.children:
        kids = [_ast_node_to_dict(c, max_depth, depth + 1) for c in node.children]
        d["children"] = [k for k in kids if k is not None]
    return d


# ════════════════════════════════════════════════════════════════
#  Interactive AST Tree Visualizer  (inline JS for standalone reports)
# ════════════════════════════════════════════════════════════════

_INTERACTIVE_TREE_CSS = """
.ast-viz-wrap{position:relative;background:#0d1117;border:1px solid #30363d;border-radius:8px;overflow:hidden;margin-top:10px;}
.ast-viz-toolbar{display:flex;gap:6px;padding:6px 10px;background:#161b22;border-bottom:1px solid #30363d;align-items:center;}
.ast-viz-toolbar button{background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:3px 10px;
  font-size:12px;cursor:pointer;transition:background .15s;}
.ast-viz-toolbar button:hover{background:#30363d;}
.ast-viz-container{width:100%;height:500px;overflow:auto;position:relative;cursor:grab;}
.ast-viz-container:active{cursor:grabbing;}
.ast-viz-container svg{min-width:100%;}
.ast-viz-node{cursor:pointer;user-select:none;}
.ast-viz-node rect{transition:opacity .15s;}
.ast-viz-node:hover rect{opacity:.85;}
.ast-viz-label{font-family:'SFMono-Regular',Consolas,monospace;pointer-events:none;}
"""

_INTERACTIVE_TREE_JS = """
(function(){
  var DATA_ID = '__AST_DATA_ID__';
  var data = window[DATA_ID];
  if(!data) return;
  var wrap = document.getElementById(DATA_ID + '_wrap');
  if(!wrap) return;

  var NODE_W = 160, NODE_H = 40, PAD_X = 20, PAD_Y = 60;
  var expanded = {'root':true};
  var colors = {
    module:'#9C27B0',program:'#9C27B0',class:'#2196F3',class_definition:'#2196F3',
    function:'#4CAF50',function_definition:'#4CAF50',method:'#8BC34A',async_function:'#00BCD4',
    import:'#FF9800',import_statement:'#FF9800',import_from_statement:'#FF9800',
    call:'#E91E63',call_expression:'#E91E63','if':'#673AB7',if_statement:'#673AB7',
    'for':'#3F51B5',for_statement:'#3F51B5','while':'#009688',while_statement:'#009688',
    'try':'#FFC107',try_statement:'#FFC107',except:'#FF5722',except_clause:'#FF5722',
    'return':'#CDDC39',return_statement:'#CDDC39'
  };
  var defColor = '#9E9E9E';

  function color(t){return colors[(t||'').toLowerCase()]||defColor;}

  // Layout: compute (x,y) for each visible node
  function layout(node, id, depth){
    var n = {id:id, node:node, x:0, y:depth*PAD_Y, depth:depth, children:[]};
    if(node.children && node.children.length && expanded[id]){
      for(var i=0;i<node.children.length;i++){
        var cid = id+'-'+i;
        var child = layout(node.children[i], cid, depth+1);
        n.children.push(child);
      }
    }
    return n;
  }

  function measureWidth(n){
    if(!n.children.length) {n.width=NODE_W+PAD_X; return n.width;}
    var w=0;
    for(var i=0;i<n.children.length;i++){w+=measureWidth(n.children[i]);}
    n.width = Math.max(w, NODE_W+PAD_X);
    return n.width;
  }

  function position(n, left){
    if(!n.children.length){n.x = left + n.width/2; return;}
    var cx = left;
    for(var i=0;i<n.children.length;i++){
      position(n.children[i], cx);
      cx += n.children[i].width;
    }
    n.x = (n.children[0].x + n.children[n.children.length-1].x)/2;
  }

  function allNodes(n, arr){arr.push(n); for(var i=0;i<n.children.length;i++) allNodes(n.children[i],arr); return arr;}
  function allEdges(n,arr){
    for(var i=0;i<n.children.length;i++){arr.push([n,n.children[i]]); allEdges(n.children[i],arr);}
    return arr;
  }

  function maxDepth(n){var d=n.depth; for(var i=0;i<n.children.length;i++){d=Math.max(d,maxDepth(n.children[i]));} return d;}

  function render(){
    var tree = layout(data, 'root', 0);
    measureWidth(tree);
    position(tree, 0);
    var nodes = allNodes(tree,[]);
    var edges = allEdges(tree,[]);
    var md = maxDepth(tree);
    var maxX = 0; for(var i=0;i<nodes.length;i++){maxX=Math.max(maxX,nodes[i].x);}
    var svgW = maxX + NODE_W + 40;
    var svgH = (md+1)*PAD_Y + NODE_H + 40;

    var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="'+svgW+'" height="'+svgH+'">';
    // Edges
    for(var i=0;i<edges.length;i++){
      var p=edges[i][0], c=edges[i][1];
      var px=p.x, py=p.y+NODE_H, cx=c.x, cy=c.y;
      var my=(py+cy)/2;
      svg+='<path d="M'+px+' '+py+' C'+px+' '+my+' '+cx+' '+my+' '+cx+' '+cy+'" fill="none" stroke="#30363d" stroke-width="1.5"/>';
    }
    // Nodes
    for(var i=0;i<nodes.length;i++){
      var n=nodes[i], nd=n.node;
      var c=color(nd.type);
      var hasKids = nd.children && nd.children.length>0;
      var isExp = expanded[n.id];
      var lbl = (nd.name || nd.type).substring(0,18);
      var sub = nd.type + (nd.loc?' L'+nd.loc.start.line:'');
      var rx=n.x-NODE_W/2, ry=n.y;
      svg+='<g class="ast-viz-node" data-id="'+n.id+'" transform="translate('+rx+','+ry+')">';
      svg+='<rect width="'+NODE_W+'" height="'+NODE_H+'" rx="6" fill="'+c+'22" stroke="'+c+'" stroke-width="1.5"/>';
      svg+='<text class="ast-viz-label" x="8" y="16" fill="#e6edf3" font-size="12" font-weight="600">'+esc(lbl)+'</text>';
      svg+='<text class="ast-viz-label" x="8" y="30" fill="#8b949e" font-size="10">'+esc(sub)+'</text>';
      if(hasKids){
        svg+='<text x="'+(NODE_W-16)+'" y="26" fill="#8b949e" font-size="14" text-anchor="middle">'+(isExp?'\\u25BC':'\\u25B6')+'</text>';
      }
      svg+='</g>';
    }
    svg+='</svg>';
    var container = wrap.querySelector('.ast-viz-container');
    container.innerHTML = svg;

    // Attach click handlers
    var gs = container.querySelectorAll('.ast-viz-node');
    for(var j=0;j<gs.length;j++){
      gs[j].addEventListener('click', function(){
        var id = this.getAttribute('data-id');
        if(expanded[id]) delete expanded[id]; else expanded[id]=true;
        render();
      });
    }
  }

  function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}

  // Toolbar
  wrap.querySelector('.ast-viz-btn-expand').onclick=function(){
    (function ex(n,id){expanded[id]=true;if(n.children)for(var i=0;i<n.children.length;i++)ex(n.children[i],id+'-'+i);})(data,'root');
    render();
  };
  wrap.querySelector('.ast-viz-btn-collapse').onclick=function(){expanded={'root':true};render();};

  // Initial expand first two levels
  expanded['root']=true;
  if(data.children) for(var i=0;i<data.children.length;i++) expanded['root-'+i]=true;
  render();
})();
"""


def _build_interactive_ast_section(ast_trace, section_id: str = "ast_interactive") -> str:
    """
    Build an interactive SVG-based AST tree visualization.
    Returns HTML with embedded JS that renders the tree client-side.
    Only used in standalone reports (not email).
    """
    if not ast_trace or not ast_trace.main_ast:
        return ""

    data_var = f"__ast_{section_id}__"
    ast_json = json_mod.dumps(
        _ast_node_to_dict(ast_trace.main_ast, max_depth=12),
        separators=(',', ':'),
    )

    js = _INTERACTIVE_TREE_JS.replace('__AST_DATA_ID__', data_var)

    return f"""
  <div class="card">
    <h2><i class="ph ph-tree-structure"></i> Interactive AST Visualization</h2>
    <p style="color:var(--fg2);font-size:13px;margin-bottom:8px;">
      Click nodes to expand/collapse. Drag to pan.</p>
    <div class="ast-viz-wrap" id="{data_var}_wrap">
      <div class="ast-viz-toolbar">
        <button class="ast-viz-btn-expand">Expand All</button>
        <button class="ast-viz-btn-collapse">Collapse All</button>
        <span style="color:#8b949e;font-size:11px;margin-left:auto;">
          <i class="ph ph-tree-structure" style="font-size:11px;"></i> {_esc(ast_trace.error_file)} &bull; Error at L{ast_trace.error_line}</span>
      </div>
      <div class="ast-viz-container"></div>
    </div>
  </div>
  <script>window['{data_var}']={ast_json};</script>
  <script>{js}</script>
"""


# ════════════════════════════════════════════════════════════════
#  AST Accordion Tree Builder
# ════════════════════════════════════════════════════════════════

class ASTAccordionBuilder:
    """
    Builds email-safe accordion HTML for AST trees using
    ``<details>`` / ``<summary>`` elements.

    Works natively in Apple Mail, iOS Mail, Thunderbird, Samsung Mail.
    In Gmail / Outlook the tree renders fully expanded (still readable).
    """

    @classmethod
    def build_tree(
        cls,
        root: ASTNode,
        error_line: int = 0,
        error_path_ids: Optional[set] = None,
        max_depth: int = 8,
        max_children: int = 30,
    ) -> str:
        """Return full accordion-tree HTML for *root*."""
        if root is None:
            return '<p style="color:#6c757d;font-style:italic;">No AST available</p>'
        error_path_ids = error_path_ids or set()
        return (
            '<div style="font-family:\'SFMono-Regular\',Consolas,\'Liberation Mono\',Menlo,monospace;'
            'font-size:13px;line-height:1.55;color:#24292e;">'
            + cls._render(root, 0, error_line, error_path_ids, max_depth, max_children)
            + '</div>'
        )

    @classmethod
    def _render(
        cls, node: ASTNode, depth: int,
        error_line: int, path_ids: set,
        max_depth: int, max_children: int,
    ) -> str:
        if depth > max_depth:
            return '<span style="color:#6c757d;font-style:italic;">... (depth limit)</span>'

        on_error_path = id(node) in path_ids
        contains_error = (
            error_line
            and node.start_line <= error_line <= node.end_line
        )

        color = _node_color(node.node_type)
        name = _esc(node.name or node.node_type or "?")
        ntype = _esc(node.node_type)
        lines = f"L{node.start_line}"
        if node.end_line and node.end_line != node.start_line:
            lines += f"&#8209;{node.end_line}"

        # Styling for error path / error containment
        bg = ""
        left_border = f"border-left:2px solid {color}55;"
        if on_error_path:
            bg = "background:rgba(220,53,69,.10);"
            left_border = "border-left:3px solid #dc3545;"
        elif contains_error:
            bg = "background:rgba(255,193,7,.08);"
            left_border = f"border-left:2px solid #ffc107;"

        # ── Type badge with icon ──
        # Map common node types to symbolic icons
        _icons = {
            "module": "&#128230;", "program": "&#128230;",
            "class": "&#128307;", "class_definition": "&#128307;",
            "function": "&#9670;", "function_definition": "&#9670;",
            "method": "&#9670;", "async_function": "&#9889;",
            "import": "&#8599;", "import_statement": "&#8599;",
            "import_from_statement": "&#8599;",
            "call": "&#9654;", "call_expression": "&#9654;",
            "if": "&#10140;", "if_statement": "&#10140;",
            "for": "&#8635;", "for_statement": "&#8635;",
            "while": "&#8635;", "while_statement": "&#8635;",
            "try": "&#9888;", "try_statement": "&#9888;",
            "except": "&#10060;", "except_clause": "&#10060;",
            "return": "&#8592;", "return_statement": "&#8592;",
        }
        icon = _icons.get((node.node_type or "").lower(), "&#9679;")

        badge = (
            f'<span style="display:inline-block;padding:1px 7px;border-radius:4px;'
            f'font-size:11px;font-weight:600;color:#fff;background:{color};'
            f'letter-spacing:.3px;">'
            f'{icon} {ntype}</span>'
        )

        # Line number badge
        line_badge = (
            f'<span style="color:#8b949e;font-size:10px;margin-left:6px;'
            f'padding:1px 5px;border-radius:3px;background:rgba(139,148,158,.12);">{lines}</span>'
        )

        # Error indicator
        error_indicator = ""
        if on_error_path and error_line and node.start_line <= error_line <= node.end_line:
            error_indicator = (
                ' <span style="color:#dc3545;font-size:10px;font-weight:700;'
                'animation:blink 1s infinite;">&#9888; ERROR</span>'
            )

        # Code snippet (first 100 chars)
        snippet = ""
        if node.code_snippet:
            short = _esc(node.code_snippet.split("\n")[0][:100])
            snippet = (
                f'<div style="color:#8b949e;font-size:11px;margin:2px 0 0 24px;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:550px;'
                f'padding:2px 6px;background:rgba(0,0,0,.04);border-radius:3px;">'
                f'<code>{short}</code></div>'
            )

        has_kids = bool(node.children) and depth < max_depth

        # ── With children -> collapsible accordion ──
        if has_kids:
            open_attr = "open" if (on_error_path or contains_error or depth < 2) else ""
            # Tree connector: ▶ (collapsed) / ▼ (expanded) via CSS
            arrow_style = (
                'display:inline-block;width:14px;font-size:10px;color:#8b949e;'
                'transition:transform .15s;margin-right:3px;'
            )
            kids = node.children[:max_children]
            children_html = "\n".join(
                cls._render(c, depth + 1, error_line, path_ids, max_depth, max_children)
                for c in kids
            )
            if len(node.children) > max_children:
                children_html += (
                    f'<div style="padding:4px 0 4px 18px;color:#8b949e;font-size:11px;">'
                    f'&#8943; {len(node.children) - max_children} more children</div>'
                )
            return (
                f'<details {open_attr} style="margin:1px 0 1px 12px;padding:3px 0 3px 10px;'
                f'{left_border}{bg}border-radius:0 4px 4px 0;">'
                f'<summary style="cursor:pointer;list-style:none;padding:3px 4px;'
                f'border-radius:4px;transition:background .15s;'
                f'user-select:none;">'
                f'<span style="{arrow_style}">&#9654;</span>'
                f'{badge} <strong style="color:#24292e;">{name}</strong>{line_badge}{error_indicator}'
                f'</summary>'
                f'{snippet}'
                f'<div style="margin-left:8px;">{children_html}</div>'
                f'</details>'
            )

        # ── Leaf node ──
        return (
            f'<div style="margin:1px 0 1px 12px;padding:4px 4px 4px 10px;'
            f'{left_border}{bg}border-radius:0 4px 4px 0;">'
            f'<span style="display:inline-block;width:14px;margin-right:3px;'
            f'font-size:10px;color:#d1d5db;">&#9679;</span>'
            f'{badge} <strong style="color:#24292e;">{name}</strong>{line_badge}{error_indicator}'
            f'{snippet}'
            f'</div>'
        )

    # Error-path breadcrumb
    @classmethod
    def build_error_path(cls, error_path: List[ASTNode]) -> str:
        """Horizontal breadcrumb showing root -> ... -> error node."""
        if not error_path:
            return '<p style="color:#6c757d;">No AST error path available</p>'

        pills = []
        for i, node in enumerate(error_path):
            is_last = i == len(error_path) - 1
            color = _node_color(node.node_type)
            name = _esc(node.name or node.node_type or "?")
            line = f"L{node.start_line}"

            if is_last:
                weight = "font-weight:700;"
                border = "border:2px solid #dc3545;"
                bg = "background:rgba(220,53,69,.12);"
                extra = "box-shadow:0 0 0 2px rgba(220,53,69,.2);"
            else:
                weight = ""
                border = f"border:1px solid {color}88;"
                bg = f"background:{color}15;"
                extra = ""

            pills.append(
                f'<span style="display:inline-flex;align-items:center;gap:4px;'
                f'padding:4px 10px;border-radius:6px;'
                f'font-size:12px;{weight}{border}{bg}{extra}white-space:nowrap;">'
                f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
                f'background:{color};"></span>'
                f'{name} <small style="opacity:.6;">({line})</small></span>'
            )

        return (
            '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;'
            'font-family:\'SFMono-Regular\',Consolas,monospace;padding:8px 0;">'
            + ' <span style="color:#8b949e;font-size:14px;">&#10132;</span> '.join(pills)
            + '</div>'
        )


# ════════════════════════════════════════════════════════════════
#  Standalone HTML Report Generator
# ════════════════════════════════════════════════════════════════

class ReportGenerator:
    """
    Builds a **full self-contained HTML page** that can be:
      - embedded in emails
      - saved to disk and served statically
      - opened directly in any browser

    All CSS is inlined so the file has zero external dependencies.
    Uses a dark theme for the standalone report.
    """

    REPORT_CSS = """
    :root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--fg:#c9d1d9;
          --fg2:#8b949e;--accent:#58a6ff;--red:#f85149;--green:#3fb950;
          --yellow:#d29922;--purple:#bc8cff;--cyan:#39d2c0;}
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
         background:var(--bg);color:var(--fg);line-height:1.6;padding:0;margin:0;}
    .rpt{max-width:960px;margin:0 auto;padding:24px;}
    .hdr{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);
         border-radius:12px;padding:32px;margin-bottom:24px;border:1px solid var(--border);}
    .hdr h1{font-size:22px;color:#fff;margin-bottom:4px;}
    .hdr p{color:#8b949e;font-size:14px;}
    .card{background:var(--surface);border:1px solid var(--border);border-radius:8px;
          padding:20px;margin-bottom:16px;}
    .card h2{font-size:16px;color:var(--accent);margin-bottom:12px;
             border-bottom:1px solid var(--border);padding-bottom:8px;}
    .badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;
           font-weight:600;color:#fff;}
    table.meta{width:100%;border-collapse:collapse;}
    table.meta td{padding:6px 0;font-size:14px;}
    table.meta td:first-child{color:var(--fg2);width:130px;}
    .code-ctx{background:#0d1117;border:1px solid var(--border);border-radius:6px;
              padding:12px;overflow-x:auto;font-family:'SFMono-Regular',Consolas,monospace;
              font-size:13px;line-height:1.5;white-space:pre;color:var(--fg);}
    .code-ctx .err-line{background:rgba(248,81,73,.15);display:block;
                        border-left:3px solid var(--red);padding-left:8px;}
    details{margin:2px 0 2px 8px;padding:2px 0 2px 10px;border-left:2px solid var(--border);}
    details[open]>summary{margin-bottom:2px;}
    summary{cursor:pointer;list-style:none;padding:3px 4px;border-radius:4px;}
    summary:hover{background:rgba(88,166,255,.06);}
    summary::-webkit-details-marker{display:none;}
    .nbadge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;
            font-weight:600;color:#fff;}
    .ref-item{background:rgba(88,166,255,.06);border-left:3px solid var(--accent);
              padding:8px 12px;margin:6px 0;border-radius:0 4px 4px 0;font-size:13px;}
    .proposal{background:var(--surface);border-left:4px solid var(--accent);
              padding:16px;margin:10px 0;border-radius:0 8px 8px 0;}
    .proposal pre{background:#0d1117;color:#e6edf3;padding:12px;border-radius:6px;
                  overflow-x:auto;margin-top:8px;font-size:13px;line-height:1.5;}
    .iter-card{background:rgba(255,255,255,.03);border:1px solid var(--border);
               border-radius:6px;padding:10px 14px;margin:6px 0;font-size:13px;}
    .progress{background:var(--border);border-radius:10px;height:18px;overflow:hidden;margin:8px 0;}
    .progress-fill{height:100%;border-radius:10px;}
    .cause{background:rgba(210,153,34,.08);border-left:4px solid var(--yellow);
           padding:10px 16px;margin:8px 0;border-radius:0 6px 6px 0;}
    .footer{text-align:center;color:var(--fg2);font-size:12px;padding:20px 0;
            border-top:1px solid var(--border);margin-top:24px;}
    @media(max-width:640px){.rpt{padding:12px;}.hdr{padding:20px;}.card{padding:14px;}}
    """ + _INTERACTIVE_TREE_CSS

    @classmethod
    def generate(
        cls,
        analysis: Optional[RootCauseAnalysis] = None,
        proposals: Optional[List[FixProposal]] = None,
        ast_trace: Optional['ASTTraceContext'] = None,
        validation_result: Optional['ValidationResult'] = None,
        title: str = "Error Analysis Report",
        subtitle: str = "AutoCure Self-Healing System",
    ) -> str:
        """Return a complete ``<!DOCTYPE html>`` page."""
        proposals = proposals or []

        error = _get_error(analysis)
        error_type = error.error_type if error else "Unknown"
        error_msg = _esc((error.message if error else "")[:500])
        source_file = str(error.source_file) if error else "unknown"
        line_number = (error.line_number or 0) if error else 0
        severity = (analysis.severity if analysis else "medium").lower()
        severity_color = _SEVERITY_COLORS.get(severity, "#6c757d")
        confidence = analysis.confidence if analysis else 0.5
        root_cause = _esc(analysis.root_cause if analysis else "Unknown")
        category = _esc(analysis.error_category if analysis else "unknown")
        affected = analysis.affected_components if analysis else []
        timestamp = (error.timestamp if error else datetime.utcnow())

        # Build sections
        validation_sec = cls._validation_section(validation_result)
        ast_sec = cls._ast_trace_section(ast_trace, line_number)
        interactive_ast_sec = _build_interactive_ast_section(ast_trace, "main_ast")
        proposals_sec = cls._proposals_section(proposals)
        deps_sec = cls._deps_section(ast_trace)
        causes_sec = cls._causes_section(validation_result)

        ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S UTC') if hasattr(timestamp, 'strftime') else str(timestamp)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/regular/style.css">
<title>{_esc(title)}</title>
<style>{cls.REPORT_CSS}</style>
</head>
<body>
<div class="rpt">

  <div class="hdr">
    <h1><i class="ph ph-first-aid-kit" style="vertical-align:middle;"></i> {_esc(title)}</h1>
    <p>{_esc(subtitle)} &bull; {ts_str}</p>
  </div>

  <!-- Error Summary -->
  <div class="card">
    <h2><i class="ph ph-warning-circle"></i> Error Summary</h2>
    <table class="meta">
      <tr><td>Type</td><td><strong>{_esc(error_type)}</strong></td></tr>
      <tr><td>Severity</td><td><span class="badge" style="background:{severity_color};">{severity.upper()}</span></td></tr>
      <tr><td>Location</td><td><code>{_esc(source_file)}:{line_number}</code></td></tr>
      <tr><td>Confidence</td><td>{confidence:.0%}</td></tr>
    </table>
    <div style="background:rgba(248,81,73,.08);padding:12px;border-radius:6px;margin-top:14px;border:1px solid rgba(248,81,73,.2);">
      <strong style="color:var(--red);">Error:</strong> <code>{error_msg}</code>
    </div>
  </div>

  {validation_sec}

  {interactive_ast_sec}

  {ast_sec}

  <!-- Root Cause -->
  <div class="card">
    <h2><i class="ph ph-magnifying-glass"></i> Root Cause Analysis</h2>
    <div style="background:rgba(88,166,255,.08);border-left:4px solid var(--accent);padding:14px;border-radius:0 6px 6px 0;">
      <p>{root_cause}</p>
    </div>
    <p style="color:var(--fg2);font-size:13px;margin-top:10px;">Category: {category}</p>
    {"<p><strong>Affected:</strong> " + ", ".join(_esc(c) for c in affected) + "</p>" if affected else ""}
  </div>

  {causes_sec}

  {proposals_sec}

  {deps_sec}

  <div class="footer">
    Generated by AutoCure Self-Healing System v2.0<br>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
  </div>

</div>
</body>
</html>"""

    # ──────────────────────────────────────────────────────────
    #  Section builders (dark theme, standalone report)
    # ──────────────────────────────────────────────────────────

    @classmethod
    def _validation_section(cls, vr) -> str:
        if not vr:
            return ""
        score = vr.confidence_score
        total = len(vr.iterations) + 1
        matching = vr.matching_iterations + 1
        bar_color = "#3fb950" if score >= 75 else ("#d29922" if score >= 50 else "#f85149")

        iter_items = ""
        for it in vr.iterations[:6]:
            icon = "&#9989;" if it.matches_initial else "&#10060;"
            iter_items += (
                f'<div class="iter-card">{icon} <strong>Iteration {it.iteration_number}</strong>'
                f' &ndash; {_esc(it.payload_variation)}'
                + (f'<br><small style="color:var(--fg2);">{_esc(it.notes[:120])}</small>' if it.notes else "")
                + '</div>'
            )

        return f"""
  <div class="card">
    <h2><i class="ph ph-chart-bar"></i> Confidence Validation</h2>
    <div style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:14px;">
      <span>Confidence Score</span><strong style="color:{bar_color};">{score:.0f}%</strong>
    </div>
    <div class="progress"><div class="progress-fill" style="width:{score}%;background:{bar_color};"></div></div>
    <p style="color:var(--fg2);font-size:12px;">Threshold 75% &bull; {matching}/{total} iterations matched</p>
    <details style="margin-top:12px;border-left:none;padding-left:0;">
      <summary style="color:var(--accent);font-weight:600;font-size:14px;">View Iteration Details</summary>
      <div style="margin-top:8px;">{iter_items or "<p style='color:var(--fg2);'>No iteration data.</p>"}</div>
    </details>
  </div>"""

    @classmethod
    def _ast_trace_section(cls, trace, error_line: int) -> str:
        """The centrepiece accordion-based AST parser trace."""
        if not trace:
            return ""

        parts: List[str] = []

        # 1. Error path breadcrumb
        if trace.error_path:
            path_ids = {id(n) for n in trace.error_path}
            path_html = ASTAccordionBuilder.build_error_path(trace.error_path)
            parts.append(
                '<div style="margin-bottom:16px;">'
                '<h3 style="font-size:14px;color:var(--fg);margin-bottom:8px;">Error Path</h3>'
                '<p style="color:var(--fg2);font-size:12px;margin-bottom:6px;">'
                'AST path from module root to the error location:</p>'
                f'{path_html}</div>'
            )
        else:
            path_ids = set()

        # 2. Code context (error line highlighted)
        if trace.error_context_code:
            code_lines = trace.error_context_code.split('\n')
            formatted = []
            for line in code_lines:
                if line.startswith(">>>"):
                    formatted.append(f'<span class="err-line">{_esc(line)}</span>')
                else:
                    formatted.append(_esc(line))
            ctx_html = "\n".join(formatted)
            parts.append(
                '<details open style="border-left:none;padding-left:0;">'
                '<summary style="font-size:14px;font-weight:600;color:var(--fg);margin-bottom:6px;">'
                '<i class="ph ph-note-pencil" style="font-size:13px;"></i> Code Context</summary>'
                f'<div class="code-ctx" style="margin-top:6px;">{ctx_html}</div></details>'
            )

        # 3. Full AST tree (accordion)
        if trace.main_ast:
            tree_html = ASTAccordionBuilder.build_tree(
                trace.main_ast,
                error_line=error_line,
                error_path_ids=path_ids,
                max_depth=8,
            )
            parts.append(
                '<details style="border-left:none;padding-left:0;">'
                '<summary style="font-size:14px;font-weight:600;color:var(--fg);margin-bottom:6px;">'
                '<i class="ph ph-tree-structure" style="font-size:13px;"></i> Full AST Tree (click to expand)</summary>'
                '<div style="background:#0d1117;border:1px solid var(--border);border-radius:6px;'
                f'padding:14px;margin-top:6px;max-height:600px;overflow:auto;">'
                f'{tree_html}</div></details>'
            )

        # 4. Cross-file references
        if trace.references:
            ref_items = ""
            for ref in trace.references[:12]:
                resolved = f" &rarr; <code>{_esc(ref.resolved_path)}</code>" if ref.resolved_path else ""
                ref_items += (
                    f'<div class="ref-item">'
                    f'<strong>{_esc(ref.symbol_name)}</strong> '
                    f'<span style="color:var(--fg2);">({ref.ref_type})</span><br>'
                    f'<small>{_esc(ref.from_file)}:{ref.line_number}{resolved}</small>'
                    f'</div>'
                )
            parts.append(
                '<details style="border-left:none;padding-left:0;">'
                '<summary style="font-size:14px;font-weight:600;color:var(--fg);margin-bottom:6px;">'
                f'<i class="ph ph-link" style="font-size:13px;"></i> Cross-File References ({len(trace.references)})</summary>'
                f'<div style="margin-top:6px;">{ref_items}</div></details>'
            )

        # 5. Referenced file ASTs
        if trace.referenced_files:
            ref_tree_parts = []
            for fpath, ast_root in list(trace.referenced_files.items())[:5]:
                mini_tree = ASTAccordionBuilder.build_tree(
                    ast_root, max_depth=3, max_children=15,
                )
                ref_tree_parts.append(
                    '<details style="border-left:none;padding-left:0;margin:8px 0;">'
                    f'<summary style="font-size:13px;color:var(--accent);">'
                    f'<i class="ph ph-file" style="font-size:12px;"></i> {_esc(os.path.basename(fpath))}'
                    f' <small style="color:var(--fg2);">({_esc(fpath)})</small></summary>'
                    '<div style="background:#0d1117;border:1px solid var(--border);border-radius:6px;'
                    f'padding:10px;margin-top:4px;max-height:300px;overflow:auto;">'
                    f'{mini_tree}</div></details>'
                )
            parts.append(
                '<details style="border-left:none;padding-left:0;">'
                '<summary style="font-size:14px;font-weight:600;color:var(--fg);margin-bottom:6px;">'
                f'<i class="ph ph-books" style="font-size:13px;"></i> Referenced File ASTs ({len(trace.referenced_files)})</summary>'
                f'<div style="margin-top:6px;">{"".join(ref_tree_parts)}</div></details>'
            )

        # 6. AI Context — what was actually sent to the AI for analysis/fix
        if getattr(trace, 'ai_context', None):
            # Convert markdown-ish context to HTML-safe pre block
            ctx_html = _esc(trace.ai_context)
            parts.append(
                '<details style="border-left:none;padding-left:0;">'
                '<summary style="font-size:14px;font-weight:600;color:var(--fg);margin-bottom:6px;">'
                '<i class="ph ph-brain" style="font-size:13px;"></i> Context Sent to AI</summary>'
                '<div style="background:rgba(88,166,255,.06);border:1px solid var(--border);'
                'border-radius:6px;padding:14px;margin-top:6px;max-height:600px;overflow:auto;">'
                f'<pre style="white-space:pre-wrap;word-wrap:break-word;font-size:12px;'
                f'line-height:1.5;color:var(--fg);margin:0;">{ctx_html}</pre>'
                '</div></details>'
            )

        if not parts:
            return ""

        return (
            '<div class="card"><h2><i class="ph ph-tree-structure"></i> AST Parser Trace</h2>'
            + "\n".join(parts)
            + '</div>'
        )

    @classmethod
    def _proposals_section(cls, proposals: List[FixProposal]) -> str:
        if not proposals:
            return ""
        items = ""
        for i, p in enumerate(proposals, 1):
            side_fx = ""
            if p.side_effects:
                side_fx = (
                    '<p style="color:var(--yellow);margin-top:8px;">'
                    '<strong><i class="ph ph-warning" style="vertical-align:middle;"></i> Side Effects:</strong> '
                    + ", ".join(_esc(e) for e in p.side_effects) + '</p>'
                )
            # Edge test cases
            tests_html = ""
            if p.test_cases:
                test_items = ""
                for j, tc in enumerate(p.test_cases, 1):
                    status_icon = '<i class="ph ph-check-circle" style="color:#3fb950;"></i>' if tc.fix_would_pass else '<i class="ph ph-x-circle" style="color:#f85149;"></i>'
                    fail_icon = '<i class="ph ph-x-circle" style="color:#f85149;"></i>' if tc.original_would_fail else '<i class="ph ph-check-circle" style="color:#3fb950;"></i>'
                    test_items += f"""
          <div style="background:rgba(255,255,255,.03);border:1px solid var(--border);
                      border-radius:6px;padding:12px;margin:6px 0;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
              <strong style="color:var(--fg);font-size:13px;">{_esc(tc.test_name or f'Test {j}')}</strong>
              <div style="font-size:11px;">
                <span style="color:#f85149;">{fail_icon} Original</span>
                <span style="margin:0 6px;color:var(--fg2);">|</span>
                <span style="color:#3fb950;">{status_icon} Fixed</span>
              </div>
            </div>
            <p style="color:var(--fg2);font-size:12px;margin-bottom:6px;">{_esc(tc.description)}</p>
            {f'<pre style="font-size:12px;line-height:1.4;">{_esc(tc.test_code)}</pre>' if tc.test_code else ''}
            {f'<p style="color:var(--green);font-size:12px;margin-top:4px;"><strong>Expected:</strong> {_esc(tc.expected_behavior)}</p>' if tc.expected_behavior else ''}
          </div>"""
                tests_html = (
                    f'<details open style="border-left:none;padding-left:0;margin-top:12px;">'
                    f'<summary style="font-size:13px;font-weight:600;color:var(--accent);cursor:pointer;">'
                    f'<i class="ph ph-test-tube" style="font-size:12px;"></i> Edge Test Cases ({len(p.test_cases)})</summary>'
                    f'{test_items}</details>'
                )
            items += f"""
      <div class="proposal">
        <h3 style="font-size:14px;color:var(--accent);margin-bottom:8px;">Proposal {i}</h3>
        <table class="meta">
          <tr><td>File</td><td><code>{_esc(p.target_file)}</code></td></tr>
          <tr><td>Confidence</td><td>{p.confidence:.0%}</td></tr>
          <tr><td>Risk</td><td>{_esc(p.risk_level)}</td></tr>
        </table>
        <p style="margin:10px 0;">{_esc(p.explanation)}</p>
        {f'<pre>{_esc(p.suggested_code)}</pre>' if p.suggested_code else ""}
        {side_fx}
        {tests_html}
      </div>"""
        return f'<div class="card"><h2><i class="ph ph-lightbulb"></i> Fix Proposals</h2>{items}</div>'

    @classmethod
    def _deps_section(cls, trace) -> str:
        if not trace or not getattr(trace, 'requirements', None):
            return ""
        reqs = trace.requirements
        all_deps = {**reqs.dependencies, **reqs.dev_dependencies}
        if not all_deps:
            return ""
        items = ""
        for name, ver in list(all_deps.items())[:20]:
            dev = (' <span class="badge" style="background:#6c757d;font-size:10px;">dev</span>'
                   if name in reqs.dev_dependencies else "")
            items += f"<li><code>{_esc(name)}</code>: {_esc(ver)}{dev}</li>"
        if len(all_deps) > 20:
            items += f'<li style="color:var(--fg2);">... and {len(all_deps) - 20} more</li>'
        return (
            f'<div class="card"><h2><i class="ph ph-package"></i> Dependencies</h2>'
            f'<p style="color:var(--fg2);font-size:13px;margin-bottom:8px;">'
            f'From <code>{_esc(reqs.manifest_file)}</code> ({_esc(reqs.language)})</p>'
            f'<ul style="padding-left:20px;font-size:13px;">{items}</ul></div>'
        )

    @classmethod
    def _causes_section(cls, vr) -> str:
        if not vr or not getattr(vr, 'possible_causes', None):
            return ""
        items = ""
        for cause in vr.possible_causes[:6]:
            items += f'<div class="cause"><strong><i class="ph ph-caret-right" style="color:var(--accent);"></i> Possible Cause</strong><p>{_esc(cause)}</p></div>'
        divergent = ""
        if getattr(vr, 'divergent_findings', None):
            for finding in vr.divergent_findings[:3]:
                divergent += (
                    '<div style="background:rgba(248,81,73,.06);border-left:4px solid var(--red);'
                    f'padding:10px 14px;margin:6px 0;border-radius:0 6px 6px 0;font-size:13px;">'
                    f'{_esc(finding)}</div>'
                )
            divergent = (
                '<h3 style="font-size:14px;color:var(--fg);margin-top:14px;">Divergent Findings</h3>'
                + divergent
            )
        return f'<div class="card"><h2><i class="ph ph-question"></i> Possible Causes</h2>{items}{divergent}</div>'


# ════════════════════════════════════════════════════════════════
#  Email-specific CSS (light theme for email clients)
# ════════════════════════════════════════════════════════════════

_EMAIL_CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
     line-height:1.6;color:#24292e;background:#f6f8fa;margin:0;padding:0;}
.container{max-width:900px;margin:0 auto;padding:20px;}
.hdr{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;
     padding:28px 30px;border-radius:10px 10px 0 0;}
.hdr-warn{background:linear-gradient(135deg,#fd7e14 0%,#dc3545 100%);}
.cnt{background:#fff;padding:28px 30px;border:1px solid #d0d7de;border-top:none;border-radius:0 0 10px 10px;}
.sec{margin:22px 0;}
.sec-title{color:#24292e;font-size:16px;border-bottom:2px solid #d0d7de;padding-bottom:8px;margin-bottom:14px;}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;color:#fff;}
table.meta{width:100%;border-collapse:collapse;}
table.meta td{padding:6px 0;font-size:14px;}
table.meta td:first-child{color:#57606a;width:130px;}
.code-box{background:#1b1f23;color:#e1e4e8;padding:14px;border-radius:6px;overflow-x:auto;
           font-family:'SFMono-Regular',Consolas,Menlo,monospace;font-size:13px;line-height:1.5;white-space:pre;}
.code-box .eline{background:rgba(248,81,73,.18);display:block;border-left:3px solid #f85149;padding-left:8px;}
details{margin:4px 0 4px 8px;padding:2px 0 2px 10px;border-left:2px solid #d0d7de;}
details[open]>summary{margin-bottom:3px;}
summary{cursor:pointer;list-style:none;padding:3px 4px;}
summary::-webkit-details-marker{display:none;}
.nbadge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;font-weight:600;color:#fff;}
.ref-item{background:#ddf4ff;border-left:3px solid #0969da;padding:8px 12px;margin:5px 0;
           border-radius:0 4px 4px 0;font-size:13px;}
.proposal-box{background:#f6f8fa;border-left:4px solid #0969da;padding:16px;margin:10px 0;
               border-radius:0 6px 6px 0;}
.proposal-box pre{background:#1b1f23;color:#e1e4e8;padding:12px;border-radius:6px;
                   overflow-x:auto;margin-top:8px;font-size:13px;}
.progress-bar{background:#d0d7de;border-radius:10px;height:18px;overflow:hidden;margin:6px 0;}
.progress-fill{height:100%;border-radius:10px;}
.iter-card{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:10px 14px;margin:5px 0;font-size:13px;}
.cause-box{background:#fff8c5;border-left:4px solid #d4a72c;padding:10px 16px;margin:8px 0;border-radius:0 6px 6px 0;}
"""


# ════════════════════════════════════════════════════════════════
#  Email Service
# ════════════════════════════════════════════════════════════════

class EmailService:
    """
    Sends rich HTML emails with accordion-based AST parser trace.

    Features:
      * High / low confidence templates based on validation
      * Accordion AST tree visualization embedded in the email
      * Full HTML report saved to ``reports/`` for online viewing
      * Code review emails for PRs
      * Zero stack-trace sections -- everything is AST parser trace
    """

    CONFIDENCE_THRESHOLD = 75.0

    def __init__(self, config=None):
        self.config = config or get_config().email

    # ──────────────────────────────────────────────────────────
    #  Analysis email (primary entry-point)
    # ──────────────────────────────────────────────────────────

    async def send_analysis_email(
        self,
        to_email: str,
        analysis: RootCauseAnalysis,
        proposals: List[FixProposal],
        ast_viz: Optional[ASTVisualization] = None,
        ast_trace: Optional['ASTTraceContext'] = None,
        validation_result: Optional['ValidationResult'] = None,
        user_id: str = "",
        branch_info: Optional[dict] = None,
    ) -> dict:
        """
        Send an error-analysis email with embedded AST parser trace.

        Also saves a full standalone HTML report to ``reports/`` indexed
        in the SQLite report store so it can be served via API.

        Returns dict with ``report_id``, ``report_path``, and ``email_sent``.
        """
        error = _get_error(analysis)
        error_type = error.error_type if error else "Unknown Error"

        # Determine confidence
        confidence_met = True
        confidence_score = 100.0
        if validation_result:
            confidence_met = validation_result.confidence_met
            confidence_score = validation_result.confidence_score
        elif hasattr(analysis, 'confidence'):
            confidence_score = analysis.confidence * 100
            confidence_met = confidence_score >= self.CONFIDENCE_THRESHOLD

        # 1. Generate & save the full standalone HTML report
        report_html = ReportGenerator.generate(
            analysis=analysis,
            proposals=proposals,
            ast_trace=ast_trace,
            validation_result=validation_result,
            title=f"Error Analysis: {error_type}",
        )
        report_path, report_id = self._save_report(
            html_content=report_html,
            error_type=error_type,
            user_id=user_id,
            analysis=analysis,
            proposals=proposals,
        )

        # 2. Build the email HTML (light theme, email-safe)
        #    Include the report URL so the user can view it online
        #    Use full absolute URL so email links work correctly
        _cfg = get_config()
        _host = os.getenv("PUBLIC_URL", f"http://localhost:{_cfg.server.port}")
        report_url = f"{_host}/api/v1/reports/{report_id}/view"

        email_sent = False
        if self.config.enable_notifications:
            if confidence_met:
                email_html = self._build_high_confidence_email(
                    analysis, proposals, ast_trace, validation_result,
                    report_path, report_url, branch_info=branch_info,
                )
            else:
                email_html = self._build_low_confidence_email(
                    analysis, proposals, ast_trace, validation_result,
                    report_path, report_url,
                )

            subject_pfx = "" if confidence_met else "LOW CONFIDENCE "
            email_sent = await self._send_email(
                to=to_email,
                subject=f"[AutoCure] {subject_pfx}Error Analysis: {error_type}",
                html_content=email_html,
            )
        else:
            logger.info("Email notifications disabled — report saved to disk only")

        return {
            "report_id": report_id,
            "report_path": report_path,
            "report_url": report_url,
            "email_sent": email_sent,
        }

    # ──────────────────────────────────────────────────────────
    #  Code-review email
    # ──────────────────────────────────────────────────────────

    async def send_code_review_email(
        self,
        to_email: str,
        review: CodeReviewResult,
    ) -> bool:
        """Send a code-review result email for a PR."""
        if not self.config.enable_notifications:
            logger.info("Email notifications disabled")
            return False

        html_content = self._build_review_email(review)
        return await self._send_email(
            to=to_email,
            subject=f"[AutoCure] Code Review: PR #{review.pr_info.pr_number} - {review.pr_info.title}",
            html_content=html_content,
        )

    # ──────────────────────────────────────────────────────────
    #  Report persistence
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _save_report(
        html_content: str,
        error_type: str,
        user_id: str = "",
        analysis: Optional[RootCauseAnalysis] = None,
        proposals: Optional[List[FixProposal]] = None,
    ) -> tuple:
        """Save HTML report to disk + index in SQLite. Returns (path, report_id)."""
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in error_type)[:40]
        filename = f"report_{ts}_{safe_name}_{uuid.uuid4().hex[:6]}.html"
        path = REPORTS_DIR / filename
        path.write_text(html_content, encoding="utf-8")

        error = _get_error(analysis) if analysis else None
        # Serialize fix proposals so the UI can retrieve and apply them
        proposals_json = ""
        if proposals:
            proposals_json = json_mod.dumps(
                [p.model_dump() for p in proposals], default=str
            )
        store = get_report_store()
        report_id = store.insert(
            file_path=str(path),
            file_name=filename,
            report_type="analysis",
            user_id=user_id,
            error_type=error_type,
            severity=(analysis.severity if analysis else "medium"),
            confidence=(analysis.confidence if analysis else 0.0),
            root_cause=(analysis.root_cause if analysis else "")[:500],
            source_file=str(error.source_file) if error else "",
            line_number=(error.line_number or 0) if error else 0,
            proposals_count=len(proposals) if proposals else 0,
            proposals_json=proposals_json,
        )
        logger.info(f"Report saved -> {path} (id={report_id})")
        return str(path), report_id

    # ══════════════════════════════════════════════════════════
    #  HIGH-confidence email template
    # ══════════════════════════════════════════════════════════

    def _build_high_confidence_email(
        self,
        analysis: RootCauseAnalysis,
        proposals: List[FixProposal],
        ast_trace,
        validation_result,
        report_path: str,
        report_url: str = "",
        branch_info: Optional[dict] = None,
    ) -> str:
        error = _get_error(analysis)
        error_type = _esc(error.error_type if error else "Unknown")
        error_msg = _esc((error.message if error else "")[:500])
        source_file = _esc(str(error.source_file) if error else "unknown")
        line_number = (error.line_number or 0) if error else 0
        severity = (analysis.severity if analysis else "medium").lower()
        sv_color = _SEVERITY_COLORS.get(severity, "#6c757d")
        root_cause = _esc(analysis.root_cause if analysis else "Unknown")
        category = _esc(analysis.error_category if analysis else "unknown")
        affected = analysis.affected_components if analysis else []
        confidence = analysis.confidence if analysis else 0.5

        confidence_score = (
            validation_result.confidence_score if validation_result
            else confidence * 100
        )

        # Build sub-sections
        validation_html = self._email_validation_section(validation_result)
        ast_html = self._email_ast_trace_section(ast_trace, line_number)
        proposals_html = self._email_proposals_section(proposals)
        deps_html = self._email_deps_section(ast_trace)

        return f"""<!DOCTYPE html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>{_EMAIL_CSS}</style></head><body>
<div class="container">
  <div class="hdr">
    <h1 style="margin:0;font-size:20px;">&#9989; Error Analysis Report</h1>
    <p style="margin:8px 0 0;opacity:.9;font-size:14px;">
      High Confidence ({confidence_score:.0f}%) &ndash; Fix Proposals Ready</p>
  </div>
  <div class="cnt">

    <!-- Confidence Banner -->
    <div style="background:#dafbe1;border:1px solid #aceebb;border-radius:6px;padding:14px;margin-bottom:18px;">
      <strong style="color:#1a7f37;">&#9989; Confidence: {confidence_score:.0f}%</strong>
      <p style="margin:4px 0 0;color:#1a7f37;font-size:13px;">
        Validation confirmed the root cause. Fix proposals are below.</p>
    </div>

    <!-- Error Summary -->
    <div class="sec">
      <h2 class="sec-title">&#128680; Error Summary</h2>
      <table class="meta">
        <tr><td>Type</td><td><strong>{error_type}</strong></td></tr>
        <tr><td>Severity</td><td><span class="badge" style="background:{sv_color};">{severity.upper()}</span></td></tr>
        <tr><td>Location</td><td><code>{source_file}:{line_number}</code></td></tr>
        <tr><td>Category</td><td>{category}</td></tr>
      </table>
      <div style="background:#fff1e5;padding:12px;border-radius:4px;margin-top:12px;border:1px solid #ffd8b5;">
        <strong>Error:</strong> <code style="color:#cf222e;">{error_msg}</code>
      </div>
    </div>

    <!-- Report link (placed early to avoid Gmail clipping) -->
    <div style="text-align:center;margin:18px 0;">
      {f'<a href="{report_url}" style="display:inline-block;padding:12px 28px;background:#0969da;color:#fff;border-radius:6px;text-decoration:none;font-weight:600;font-size:15px;">&#128196; View Full Report Online</a>' if report_url else ''}
      <p style="color:#57606a;font-size:12px;margin-top:6px;">The full report contains interactive AST visualization, detailed proposals, and more.</p>
    </div>

    {self._email_branch_section(branch_info)}

    <!-- Root Cause -->
    <div class="sec">
      <h2 class="sec-title">&#128269; Root Cause Analysis</h2>
      <div style="background:#ddf4ff;border-left:4px solid #0969da;padding:14px;border-radius:0 6px 6px 0;">
        <p style="margin:0;">{root_cause}</p>
      </div>
      {"<p style='margin-top:8px;'><strong>Affected:</strong> " + ", ".join(_esc(c) for c in affected) + "</p>" if affected else ""}
    </div>

    {validation_html}
    {proposals_html}

    <!-- AST Trace (collapsed to keep email compact) -->
    <details style="border:1px solid #d0d7de;border-radius:6px;padding:12px;margin:16px 0;">
      <summary style="cursor:pointer;font-size:15px;font-weight:600;color:#0969da;list-style:none;padding:4px;">
        &#127795; AST Parser Trace (click to expand)
      </summary>
      <div style="margin-top:10px;">
        {ast_html}
      </div>
    </details>

    {deps_html}

    <div style="margin-top:24px;padding-top:16px;border-top:1px solid #d0d7de;color:#57606a;font-size:12px;text-align:center;">
      Generated by AutoCure Self-Healing System v2.0 &bull; {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
    </div>
  </div>
</div></body></html>"""

    # ══════════════════════════════════════════════════════════
    #  LOW-confidence email template
    # ══════════════════════════════════════════════════════════

    def _build_low_confidence_email(
        self,
        analysis: RootCauseAnalysis,
        proposals: List[FixProposal],
        ast_trace,
        validation_result,
        report_path: str,
        report_url: str = "",
    ) -> str:
        error = _get_error(analysis)
        error_type = _esc(error.error_type if error else "Unknown")
        error_msg = _esc((error.message if error else "")[:500])
        source_file = _esc(str(error.source_file) if error else "unknown")
        line_number = (error.line_number or 0) if error else 0
        severity = (analysis.severity if analysis else "medium").lower()
        sv_color = _SEVERITY_COLORS.get(severity, "#6c757d")
        category = _esc(analysis.error_category if analysis else "unknown")

        confidence_score = (
            validation_result.confidence_score if validation_result
            else (analysis.confidence * 100 if analysis else 50)
        )

        validation_html = self._email_validation_section(validation_result)
        ast_html = self._email_ast_trace_section(ast_trace, line_number)
        causes_html = self._email_causes_section(validation_result)
        deps_html = self._email_deps_section(ast_trace)

        return f"""<!DOCTYPE html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>{_EMAIL_CSS}</style></head><body>
<div class="container">
  <div class="hdr hdr-warn">
    <h1 style="margin:0;font-size:20px;">&#9888;&#65039; Error Analysis Report</h1>
    <p style="margin:8px 0 0;opacity:.9;font-size:14px;">
      Low Confidence ({confidence_score:.0f}%) &ndash; Manual Review Recommended</p>
  </div>
  <div class="cnt">

    <!-- Warning Banner -->
    <div style="background:#fff8c5;border:1px solid #d4a72c;border-radius:6px;padding:14px;margin-bottom:18px;">
      <strong style="color:#9a6700;">&#9888;&#65039; Low Confidence: {confidence_score:.0f}%</strong>
      <p style="margin:4px 0 0;color:#9a6700;font-size:13px;">
        Validation iterations were inconsistent. Possible causes are listed instead of fix proposals.</p>
    </div>

    <!-- Error Summary -->
    <div class="sec">
      <h2 class="sec-title">&#128680; Error Summary</h2>
      <table class="meta">
        <tr><td>Type</td><td><strong>{error_type}</strong></td></tr>
        <tr><td>Severity</td><td><span class="badge" style="background:{sv_color};">{severity.upper()}</span></td></tr>
        <tr><td>Location</td><td><code>{source_file}:{line_number}</code></td></tr>
        <tr><td>Category</td><td>{category}</td></tr>
      </table>
      <div style="background:#fff1e5;padding:12px;border-radius:4px;margin-top:12px;border:1px solid #ffd8b5;">
        <strong>Error:</strong> <code style="color:#cf222e;">{error_msg}</code>
      </div>
    </div>

    <!-- Report link (placed early to avoid Gmail clipping) -->
    <div style="text-align:center;margin:18px 0;">
      {f'<a href="{report_url}" style="display:inline-block;padding:12px 28px;background:#9a6700;color:#fff;border-radius:6px;text-decoration:none;font-weight:600;font-size:15px;">&#128196; View Full Report Online</a>' if report_url else ''}
      <p style="color:#57606a;font-size:12px;margin-top:6px;">The full report has interactive AST visualization and detailed analysis.</p>
    </div>

    {validation_html}
    {causes_html}

    <!-- AST Trace (collapsed to keep email compact) -->
    <details style="border:1px solid #d0d7de;border-radius:6px;padding:12px;margin:16px 0;">
      <summary style="cursor:pointer;font-size:15px;font-weight:600;color:#9a6700;list-style:none;padding:4px;">
        &#127795; AST Parser Trace (click to expand)
      </summary>
      <div style="margin-top:10px;">
        {ast_html}
      </div>
    </details>

    {deps_html}

    <div style="margin-top:24px;padding-top:16px;border-top:1px solid #d0d7de;color:#57606a;font-size:12px;text-align:center;">
      <strong>&#9888;&#65039; Manual investigation recommended.</strong><br>
      Generated by AutoCure Self-Healing System v2.0 &bull; {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
    </div>
  </div>
</div></body></html>"""

    # ══════════════════════════════════════════════════════════
    #  Code Review email
    # ══════════════════════════════════════════════════════════

    def _build_review_email(self, review: CodeReviewResult) -> str:
        pr = review.pr_info

        assess_colors = {"approve": "#1a7f37", "request_changes": "#cf222e", "comment": "#9a6700"}
        assess_icons = {"approve": "&#9989;", "request_changes": "&#10060;", "comment": "&#128172;"}
        assess_color = assess_colors.get(review.overall_assessment, "#57606a")
        assess_icon = assess_icons.get(review.overall_assessment, "&#128221;")

        comments_html = ""
        for c in review.comments:
            sev_colors = {"error": "#cf222e", "critical": "#cf222e", "warning": "#bf8700",
                          "suggestion": "#0969da", "info": "#57606a", "nitpick": "#57606a"}
            c_color = sev_colors.get(c.severity, "#57606a")
            snippet_html = ""
            if c.code_snippet:
                snippet_html = (
                    '<div style="background:#f0f4f8;padding:8px;border-radius:4px;margin-top:4px;font-size:12px;">'
                    f'<strong style="color:#57606a;">Context:</strong><br>'
                    f'<code style="white-space:pre;font-size:11px;">{_esc(c.code_snippet[:300])}</code></div>'
                )
            comments_html += f"""
      <div style="border-left:4px solid {c_color};padding:10px 14px;margin:8px 0;background:#f6f8fa;border-radius:0 4px 4px 0;">
        <p style="margin:0 0 4px;color:#57606a;font-size:12px;">
          {_esc(c.file_path)}:{c.line_number or "?"} &bull;
          <span style="color:{c_color};font-weight:600;">{c.severity.upper()}</span> &bull;
          {_esc(c.comment_type)}
        </p>
        <p style="margin:4px 0;">{_esc(c.message)}</p>
        {snippet_html}
        {f'<pre style="background:#1b1f23;color:#e1e4e8;padding:10px;font-size:12px;border-radius:4px;margin-top:6px;">{_esc(c.suggested_fix)}</pre>' if c.suggested_fix else ""}
      </div>"""

        highlights_html = ""
        if review.highlights:
            highlights_html = (
                '<div class="sec"><h3 class="sec-title">&#10024; Highlights</h3><ul>'
                + "".join(f"<li>{_esc(h)}</li>" for h in review.highlights) + "</ul></div>"
            )

        ast_insights_html = ""
        if review.ast_insights:
            ast_insights_html = (
                '<div class="sec"><h2 class="sec-title">&#127795; AST Analysis Insights</h2>'
                '<div style="background:#ddf4ff;border-left:4px solid #0969da;padding:14px;border-radius:0 6px 6px 0;">'
                f'<p style="margin:0;font-size:13px;">{_esc(review.ast_insights)}</p>'
                '</div></div>'
            )

        return f"""<!DOCTYPE html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>{_EMAIL_CSS}</style></head><body>
<div class="container">
  <div class="hdr">
    <h1 style="margin:0;font-size:20px;">&#128221; Code Review Report</h1>
    <p style="margin:8px 0 0;opacity:.9;font-size:14px;">PR #{pr.pr_number}: {_esc(pr.title)}</p>
  </div>
  <div class="cnt">

    <div style="text-align:center;padding:20px;background:#f6f8fa;border-radius:8px;margin-bottom:18px;">
      <div style="font-size:42px;">{assess_icon}</div>
      <div style="font-size:18px;font-weight:600;color:{assess_color};text-transform:uppercase;margin-top:6px;">
        {review.overall_assessment.replace('_', ' ')}</div>
    </div>

    <div class="sec">
      <h2 class="sec-title">&#128203; Summary</h2>
      <p>{_esc(review.summary)}</p>
    </div>

    <div class="sec">
      <h3 class="sec-title">&#128256; PR Details</h3>
      <table class="meta">
        <tr><td>Base</td><td>{_esc(pr.target_branch)}</td></tr>
        <tr><td>Head</td><td>{_esc(pr.source_branch)}</td></tr>
        <tr><td>Author</td><td>{_esc(pr.author)}</td></tr>
        <tr><td>Reviewed</td><td>{review.reviewed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</td></tr>
      </table>
    </div>

    <div class="sec">
      <h2 class="sec-title">&#128172; Review Comments ({len(review.comments)})</h2>
      {comments_html or '<p style="color:#57606a;">No comments.</p>'}
    </div>

    {ast_insights_html}
    {highlights_html}

    <div style="margin-top:24px;padding-top:16px;border-top:1px solid #d0d7de;color:#57606a;font-size:12px;text-align:center;">
      Automated code review &bull; Human judgement should be applied before merging.<br>
      AutoCure Self-Healing System v2.0
    </div>
  </div>
</div></body></html>"""

    # ══════════════════════════════════════════════════════════
    #  Reusable email sub-section builders
    # ══════════════════════════════════════════════════════════

    def _email_validation_section(self, vr) -> str:
        """Confidence validation progress bar + iteration details."""
        if not vr:
            return ""
        score = vr.confidence_score
        total = len(vr.iterations) + 1
        matching = vr.matching_iterations + 1
        bar_color = "#1a7f37" if score >= 75 else ("#9a6700" if score >= 50 else "#cf222e")

        iter_items = ""
        for it in vr.iterations[:6]:
            icon = "&#9989;" if it.matches_initial else "&#10060;"
            iter_items += (
                f'<div class="iter-card">{icon} <strong>Iteration {it.iteration_number}</strong>'
                f' &ndash; {_esc(it.payload_variation)}'
                + (f'<br><small style="color:#57606a;">{_esc(it.notes[:120])}</small>' if it.notes else "")
                + '</div>'
            )

        return f"""
    <div class="sec">
      <h2 class="sec-title">&#128202; Confidence Validation</h2>
      <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
        <span>Confidence Score</span><strong style="color:{bar_color};">{score:.0f}%</strong>
      </div>
      <div class="progress-bar"><div class="progress-fill" style="width:{score}%;background:{bar_color};"></div></div>
      <p style="color:#57606a;font-size:12px;margin-top:4px;">Threshold 75% &bull; {matching}/{total} matched</p>
      <details style="border-left:none;padding-left:0;margin-top:12px;">
        <summary style="color:#0969da;font-weight:600;font-size:13px;">View Iteration Details</summary>
        <div style="margin-top:6px;">{iter_items or "<p style='color:#57606a;'>No data.</p>"}</div>
      </details>
    </div>"""

    def _email_ast_trace_section(self, trace, error_line: int) -> str:
        """
        THE centrepiece: accordion-based AST parser trace in the email.
        Replaces legacy stack-trace sections entirely.
        Shows: error path breadcrumb, code context, full AST accordion
        tree, cross-file references, and referenced file ASTs.
        """
        if not trace:
            return ""

        parts: List[str] = []

        # 1. Error path breadcrumb
        if trace.error_path:
            path_ids = {id(n) for n in trace.error_path}
            path_html = ASTAccordionBuilder.build_error_path(trace.error_path)
            parts.append(
                '<div style="margin-bottom:14px;">'
                '<h4 style="font-size:14px;margin-bottom:6px;">AST Error Path</h4>'
                '<p style="color:#57606a;font-size:12px;margin-bottom:6px;">'
                'Trace from module root to the error location:</p>'
                f'{path_html}</div>'
            )
        else:
            path_ids = set()

        # 2. Code context
        if trace.error_context_code:
            code_lines = trace.error_context_code.split('\n')
            fmt = []
            for line in code_lines:
                if line.startswith(">>>"):
                    fmt.append(f'<span class="eline">{_esc(line)}</span>')
                else:
                    fmt.append(_esc(line))
            parts.append(
                '<details style="border-left:none;padding-left:0;">'
                '<summary style="font-size:14px;font-weight:600;">&#128221; Code Context</summary>'
                f'<div class="code-box" style="margin-top:6px;">{chr(10).join(fmt)}</div></details>'
            )

        # 3. Full AST accordion tree (limited depth for email)
        if trace.main_ast:
            tree_html = ASTAccordionBuilder.build_tree(
                trace.main_ast,
                error_line=error_line,
                error_path_ids=path_ids,
                max_depth=4,
                max_children=10,
            )
            parts.append(
                '<details style="border-left:none;padding-left:0;">'
                '<summary style="font-size:14px;font-weight:600;">'
                '&#127794; Full AST Tree (click to expand)</summary>'
                '<div style="background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;'
                f'padding:14px;margin-top:6px;max-height:500px;overflow:auto;">'
                f'{tree_html}</div></details>'
            )

        # 4. Cross-file references
        if trace.references:
            ref_items = ""
            for ref in trace.references[:12]:
                resolved = f" &rarr; <code>{_esc(ref.resolved_path)}</code>" if ref.resolved_path else ""
                ref_items += (
                    f'<div class="ref-item"><strong>{_esc(ref.symbol_name)}</strong> '
                    f'<span style="color:#57606a;">({ref.ref_type})</span><br>'
                    f'<small>{_esc(ref.from_file)}:{ref.line_number}{resolved}</small></div>'
                )
            parts.append(
                '<details style="border-left:none;padding-left:0;">'
                '<summary style="font-size:14px;font-weight:600;">'
                f'&#128279; References ({len(trace.references)})</summary>'
                f'<div style="margin-top:6px;">{ref_items}</div></details>'
            )

        # 5. Referenced file ASTs (limited for email compactness)
        if trace.referenced_files:
            rf_parts = []
            for fpath, ast_root in list(trace.referenced_files.items())[:3]:
                mini = ASTAccordionBuilder.build_tree(ast_root, max_depth=2, max_children=8)
                rf_parts.append(
                    '<details style="border-left:none;margin:6px 0;padding-left:0;">'
                    f'<summary style="font-size:13px;color:#0969da;">'
                    f'&#128196; {_esc(os.path.basename(fpath))}</summary>'
                    '<div style="background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;'
                    f'padding:10px;margin-top:4px;max-height:280px;overflow:auto;">{mini}</div></details>'
                )
            parts.append(
                '<details style="border-left:none;padding-left:0;">'
                '<summary style="font-size:14px;font-weight:600;">'
                f'&#128218; Referenced ASTs ({len(trace.referenced_files)})</summary>'
                f'<div style="margin-top:6px;">{"".join(rf_parts)}</div></details>'
            )

        # 6. AI Context — what was actually sent to the AI
        if getattr(trace, 'ai_context', None):
            ctx_html = _esc(trace.ai_context)
            parts.append(
                '<details style="border-left:none;padding-left:0;">'
                '<summary style="font-size:14px;font-weight:600;">'
                '&#129504; Context Sent to AI</summary>'
                '<div style="background:#f0f6ff;border:1px solid #d0d7de;'
                'border-radius:6px;padding:14px;margin-top:6px;max-height:600px;overflow:auto;">'
                f'<pre style="white-space:pre-wrap;word-wrap:break-word;font-size:12px;'
                f'line-height:1.5;color:#24292f;margin:0;">{ctx_html}</pre>'
                '</div></details>'
            )

        if not parts:
            return ""

        return (
            '<div class="sec"><h2 class="sec-title">&#127795; AST Parser Trace</h2>'
            + "\n".join(parts)
            + '</div>'
        )

    def _email_proposals_section(self, proposals: List[FixProposal]) -> str:
        if not proposals:
            return (
                '<div class="sec"><h2 class="sec-title">&#128161; Fix Proposals</h2>'
                '<p style="color:#57606a;">None generated.</p></div>'
            )
        items = ""
        for i, p in enumerate(proposals, 1):
            sfx = ""
            if p.side_effects:
                sfx = (
                    '<p style="color:#9a6700;margin-top:8px;">'
                    '<strong>&#9888;&#65039; Side Effects:</strong> '
                    + ", ".join(_esc(e) for e in p.side_effects) + '</p>'
                )
            # Edge test cases (email-safe)
            tests_html = ""
            if p.test_cases:
                test_items = ""
                for j, tc in enumerate(p.test_cases, 1):
                    orig_color = "#cf222e" if tc.original_would_fail else "#1a7f37"
                    orig_label = "FAIL" if tc.original_would_fail else "PASS"
                    fix_color = "#1a7f37" if tc.fix_would_pass else "#cf222e"
                    fix_label = "PASS" if tc.fix_would_pass else "FAIL"
                    test_items += f"""
              <div style="background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:10px 12px;margin:6px 0;">
                <div style="margin-bottom:4px;">
                  <strong style="font-size:13px;color:#24292f;">{_esc(tc.test_name or f'Test {j}')}</strong>
                  <span style="float:right;font-size:11px;">
                    <span style="color:{orig_color};font-weight:600;">Original: {orig_label}</span>
                    &nbsp;|&nbsp;
                    <span style="color:{fix_color};font-weight:600;">Fixed: {fix_label}</span>
                  </span>
                </div>
                <p style="color:#57606a;font-size:12px;margin:4px 0;">{_esc(tc.description)}</p>
                {f'<pre style="background:#f0f0f0;padding:8px;border-radius:4px;font-size:12px;line-height:1.4;overflow-x:auto;">{_esc(tc.test_code)}</pre>' if tc.test_code else ''}
                {f'<p style="color:#1a7f37;font-size:12px;margin-top:4px;"><strong>Expected:</strong> {_esc(tc.expected_behavior)}</p>' if tc.expected_behavior else ''}
              </div>"""
                tests_html = (
                    f'<div style="border-top:1px solid #d0d7de;margin-top:12px;padding-top:10px;">'
                    f'<strong style="font-size:13px;color:#0969da;">&#129514; Edge Test Cases ({len(p.test_cases)})</strong>'
                    f'{test_items}</div>'
                )
            items += f"""
      <div class="proposal-box">
        <h4 style="color:#0969da;margin-bottom:8px;">Proposal {i}</h4>
        <table class="meta">
          <tr><td>File</td><td><code>{_esc(p.target_file)}</code></td></tr>
          <tr><td>Confidence</td><td>{p.confidence:.0%}</td></tr>
          <tr><td>Risk</td><td>{_esc(p.risk_level)}</td></tr>
        </table>
        <p style="margin:10px 0;">{_esc(p.explanation)}</p>
        {f'<pre>{_esc(p.suggested_code)}</pre>' if p.suggested_code else ""}
        {sfx}
        {tests_html}
      </div>"""
        return f'<div class="sec"><h2 class="sec-title">&#128161; Fix Proposals</h2>{items}</div>'

    def _email_causes_section(self, vr) -> str:
        """Build possible-causes section for low-confidence emails."""
        if not vr:
            return ""
        items = ""
        if hasattr(vr, 'possible_causes') and vr.possible_causes:
            for cause in vr.possible_causes[:6]:
                items += (
                    f'<div class="cause-box"><strong>&#128312; Possible Cause</strong>'
                    f'<p style="margin:4px 0 0;">{_esc(cause)}</p></div>'
                )
        divergent = ""
        if hasattr(vr, 'divergent_findings') and vr.divergent_findings:
            for f in vr.divergent_findings[:3]:
                divergent += (
                    '<div style="background:#ffebe9;border-left:4px solid #cf222e;'
                    f'padding:10px 14px;margin:6px 0;border-radius:0 6px 6px 0;font-size:13px;">{_esc(f)}</div>'
                )
            divergent = '<h4 style="margin-top:12px;">Divergent Findings</h4>' + divergent
        if not items and not divergent:
            return ""
        return (
            '<div class="sec"><h2 class="sec-title">&#129300; Possible Causes</h2>'
            '<p style="color:#57606a;font-size:13px;margin-bottom:10px;">'
            'Confidence below 75% &ndash; investigate these possible causes:</p>'
            f'{items}{divergent}</div>'
        )

    def _email_deps_section(self, trace) -> str:
        """Dependencies section from project manifest."""
        if not trace or not getattr(trace, 'requirements', None):
            return ""
        reqs = trace.requirements
        all_deps = {**reqs.dependencies, **reqs.dev_dependencies}
        if not all_deps:
            return ""
        items = ""
        for name, ver in list(all_deps.items())[:15]:
            dev = (' <span class="badge" style="background:#6c757d;font-size:10px;">dev</span>'
                   if name in reqs.dev_dependencies else "")
            items += f"<li><code>{_esc(name)}</code>: {_esc(ver)}{dev}</li>"
        if len(all_deps) > 15:
            items += f'<li style="color:#57606a;">... and {len(all_deps) - 15} more</li>'
        return (
            f'<div class="sec"><h2 class="sec-title">&#128230; Dependencies</h2>'
            f'<p style="color:#57606a;font-size:13px;margin-bottom:6px;">'
            f'From <code>{_esc(reqs.manifest_file)}</code> ({_esc(reqs.language)})</p>'
            f'<ul style="padding-left:20px;font-size:13px;">{items}</ul></div>'
        )

    def _email_branch_section(self, branch_info: Optional[dict]) -> str:
        """Branch push status section for the email, shown just below 'View Report' button."""
        if not branch_info:
            return ""
        status = branch_info.get("fix_status", "pending")
        branch_name = _esc(branch_info.get("branch_name", ""))
        compare_url = branch_info.get("compare_url", "")
        files_mod = branch_info.get("files_modified", 0)

        if status == "pushed" and compare_url:
            return (
                '<div style="background:#dafbe1;border:1px solid #aceebb;border-radius:8px;'
                'padding:16px;margin:0 0 18px;text-align:center;">'
                '<p style="margin:0 0 4px;font-size:15px;font-weight:700;color:#1a7f37;">'
                '&#9989; Fix Branch Pushed Successfully</p>'
                f'<p style="margin:0 0 10px;color:#1a7f37;font-size:13px;">'
                f'Branch: <code style="background:#aceebb;padding:2px 6px;border-radius:3px;">{branch_name}</code>'
                f' &bull; {files_mod} file(s) modified</p>'
                f'<a href="{compare_url}" style="display:inline-block;padding:10px 24px;'
                'background:#1a7f37;color:#fff;border-radius:6px;text-decoration:none;'
                'font-weight:600;font-size:14px;">&#128279; View Changes on GitHub</a>'
                '</div>'
            )
        elif status == "failed":
            err_msg = _esc(branch_info.get("error", "Unknown error"))
            return (
                '<div style="background:#ffebe9;border:1px solid #ffcecb;border-radius:8px;'
                'padding:14px;margin:0 0 18px;text-align:center;">'
                '<p style="margin:0 0 4px;font-size:14px;font-weight:600;color:#cf222e;">'
                '&#10060; Auto-Fix Push Failed</p>'
                f'<p style="margin:0;color:#cf222e;font-size:12px;">{err_msg}</p>'
                '</div>'
            )
        # no_token, low_confidence, pending — don't show anything
        return ""

    # ══════════════════════════════════════════════════════════
    #  SMTP sender
    # ══════════════════════════════════════════════════════════

    async def send_generic_email(self, to_email: str, subject: str, html_body: str) -> bool:
        """Send a generic HTML email (for fix notifications, etc.)."""
        if not self.config.enable_notifications:
            return False
        return await self._send_email(to=to_email, subject=subject, html_content=html_body)

    async def _send_email(self, to: str, subject: str, html_content: str) -> bool:
        """Build MIME message and send via SMTP (TLS)."""
        if not self.config.sender_email or not self.config.sender_password:
            logger.error("Email sender credentials not configured")
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.sender_email
            msg["To"] = to
            msg.attach(MIMEText(html_content, "html"))

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_smtp, msg)
            logger.info(f"Email sent to {to}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def _send_smtp(self, msg: MIMEMultipart):
        """Blocking SMTP send (called via executor)."""
        with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
            server.starttls()
            server.login(self.config.sender_email, self.config.sender_password)
            server.send_message(msg)


# ════════════════════════════════════════════════════════════════
#  Singleton
# ════════════════════════════════════════════════════════════════

_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create the email-service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
