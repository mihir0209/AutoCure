"""
Unit Tests for AST Service and AST Trace Service
=================================================
Validates isolated AST parsing (Python, JavaScript, TypeScript) and
error tracing functionality without requiring a running server or external AI APIs.
"""

import os
import sys
import tempfile
from pathlib import Path
import pytest

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.ast_service import ASTService, get_ast_service
from services.ast_trace_service import ASTTraceService, get_ast_trace_service, Reference, ASTTraceContext
from services.ai_analyzer import AIAnalyzer
from utils.models import DetectedError, ASTNode


@pytest.fixture
def ast_service():
    return ASTService()


@pytest.fixture
def ast_trace_service():
    return ASTTraceService()


# ============================================================================
# 1. ASTService - Python Parsing
# ============================================================================

def test_ast_service_python_parse_code(ast_service):
    """Test parsing Python code into an ASTNode tree."""
    python_code = '''
def calculate_average(numbers: list[float]) -> float:
    if not numbers:
        return 0.0
    total = sum(numbers)
    return total / len(numbers)

class Calculator:
    def add(self, a, b):
        return a + b
'''
    root = ast_service.parse_code(python_code, "python", "calc.py")
    assert root is not None, "Root AST node should not be None"
    assert root.node_type == "module"
    assert root.file_path == "calc.py"
    assert len(root.children) >= 2

    # Verify function definition node exists
    func_nodes = [c for c in root.children if "function_definition" in c.node_type]
    assert len(func_nodes) >= 1
    func_node = func_nodes[0]
    assert func_node.name == "calculate_average"
    assert func_node.start_line == 2

    # Verify class definition node exists
    class_nodes = [c for c in root.children if "class_definition" in c.node_type]
    assert len(class_nodes) >= 1
    class_node = class_nodes[0]
    assert class_node.name == "Calculator"


# ============================================================================
# 2. ASTService - JavaScript Parsing
# ============================================================================

def test_ast_service_javascript_parse_code(ast_service):
    """Test parsing JavaScript code (ES6+ and classes)."""
    js_code = '''
import { formatCurrency } from './utils';

class PaymentProcessor {
    constructor(gateway) {
        this.gateway = gateway;
    }

    async processPayment(amount, currency = 'USD') {
        if (amount <= 0) {
            throw new Error('Invalid amount');
        }
        return this.gateway.charge({ amount, currency });
    }
}

export default PaymentProcessor;
'''
    root = ast_service.parse_code(js_code, "javascript", "payment.js")
    assert root is not None
    assert root.node_type == "program"
    assert root.file_path == "payment.js"
    assert len(root.children) >= 1

    # Check for class declaration
    class_nodes = [
        c for c in root.children
        if "class_declaration" in c.node_type or "class" in c.node_type
    ]
    assert len(class_nodes) >= 1
    assert class_nodes[0].name == "PaymentProcessor"


# ============================================================================
# 3. ASTService - TypeScript Parsing
# ============================================================================

def test_ast_service_typescript_parse_code(ast_service):
    """Test parsing TypeScript code (types, interfaces, generics)."""
    ts_code = '''
interface User {
    id: string;
    username: string;
    email: string;
    roles: string[];
}

function findUserById<T extends User>(users: T[], id: string): T | undefined {
    return users.find((user: T) => user.id === id);
}

export { User, findUserById };
'''
    root = ast_service.parse_code(ts_code, "typescript", "user.ts")
    assert root is not None
    assert root.node_type == "program"
    assert root.file_path == "user.ts"

    # Verify children count and function definition
    assert len(root.children) >= 2
    func_nodes = [c for c in root.children if "function_declaration" in c.node_type]
    assert len(func_nodes) >= 1
    assert func_nodes[0].name == "findUserById"


# ============================================================================
# 4. ASTService - Language Detection
# ============================================================================

def test_ast_service_detect_language(ast_service):
    """Test file extension to language mapping."""
    assert ast_service.detect_language("app.py") == "python"
    assert ast_service.detect_language("index.js") == "javascript"
    assert ast_service.detect_language("server.ts") == "typescript"
    assert ast_service.detect_language("component.tsx") == "tsx"
    assert ast_service.detect_language("main.go") == "go"
    assert ast_service.detect_language("lib.rs") == "rust"
    assert ast_service.detect_language("unknown.xyz123") is None


# ============================================================================
# 5. ASTTraceService - Python Error Tracing
# ============================================================================

def test_ast_trace_service_trace_error_python(ast_trace_service):
    """Test AST tracing on a Python file to locate the error node."""
    code = '''import os

def process_data(items, index):
    header = "Processing"
    result = items[index]
    return result

def main():
    items = [1, 2, 3]
    return process_data(items, 10)
'''
    # Error at line 5: result = items[index]
    trace = ast_trace_service.trace_error(
        error_file="service.py",
        error_line=5,
        repo_path="",
        source_code=code,
    )

    assert trace is not None
    assert trace.error_file == "service.py"
    assert trace.error_line == 5
    assert trace.main_ast is not None
    assert trace.main_ast.node_type == "module"

    # Context code must contain marked line
    assert ">>>    5 |     result = items[index]" in trace.error_context_code

    # Verify path from root to line 5
    assert len(trace.error_path) > 0
    node_types = [n.node_type for n in trace.error_path]
    assert "module" in node_types
    assert "function_definition" in node_types

    # Find the function node on path
    func_node = next(n for n in trace.error_path if n.node_type == "function_definition")
    assert func_node.name == "process_data"


# ============================================================================
# 6. ASTTraceService - JavaScript Error Tracing
# ============================================================================

def test_ast_trace_service_trace_error_javascript(ast_trace_service):
    """Test AST tracing on a JavaScript file to locate error node."""
    code = '''const calculateTotal = (cart) => {
    let subtotal = 0;
    cart.items.forEach(item => {
        subtotal += item.price * item.quantity;
    });
    return subtotal;
};
'''
    # Error at line 3: cart.items.forEach
    trace = ast_trace_service.trace_error(
        error_file="cart.js",
        error_line=3,
        repo_path="",
        source_code=code,
    )

    assert trace is not None
    assert trace.error_file == "cart.js"
    assert trace.error_line == 3
    assert trace.main_ast is not None
    assert ">>>    3 |     cart.items.forEach(item => {" in trace.error_context_code
    assert len(trace.error_path) > 0


def test_ast_trace_service_trace_error_typescript(ast_trace_service):
    """Test AST tracing on a TypeScript file to locate error node."""
    code = '''interface Order {
    orderId: string;
    items: string[];
}

export function processOrder(order: Order | null): number {
    const count = order.items.length;
    return count;
}
'''
    # Error at line 7: order.items.length (null dereference)
    trace = ast_trace_service.trace_error(
        error_file="order.ts",
        error_line=7,
        repo_path="",
        source_code=code,
    )

    assert trace is not None
    assert trace.error_file == "order.ts"
    assert trace.error_line == 7
    assert trace.main_ast is not None
    assert ">>>    7 |     const count = order.items.length;" in trace.error_context_code
    assert len(trace.error_path) > 0


# ============================================================================
# 7. ASTTraceService - Cross-File Reference Extraction
# ============================================================================

def test_ast_trace_service_references(ast_trace_service):
    """Test extracting import and module references from source code."""
    py_code = '''import sys
from os.path import join, dirname
from services.auth import AuthService
import database
'''
    py_refs = ast_trace_service._extract_references(py_code, "main.py")
    assert len(py_refs) >= 2
    to_files = [r.to_file for r in py_refs]
    assert any("services/auth" in tf or "services.auth" in tf for tf in to_files)

    js_code = '''import { helper } from './utils/helper';
const db = require('./database/client');
import React from 'react';
'''
    js_refs = ast_trace_service._extract_references(js_code, "app.js")
    assert len(js_refs) >= 2
    relative_refs = [r for r in js_refs if r.to_file.startswith(".")]
    assert len(relative_refs) >= 2


# ============================================================================
# 8. ASTTraceService - Project Requirements Detection
# ============================================================================

def test_ast_trace_service_requirements_detection(ast_trace_service):
    """Test detecting project requirements manifest files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        req_file = Path(temp_dir) / "requirements.txt"
        req_file.write_text("fastapi>=0.109.0\nuvicorn>=0.27.0\npydantic>=2.5.0\n")

        reqs = ast_trace_service.detect_requirements(temp_dir)
        assert reqs is not None
        assert reqs.language == "python"
        assert reqs.manifest_file == "requirements.txt"
        assert "fastapi" in reqs.dependencies
        assert "uvicorn" in reqs.dependencies


# ============================================================================
# 9. ASTTraceService - Build Rich AI Context
# ============================================================================

def test_ast_trace_build_ai_context(ast_trace_service):
    """Test building structured AI markdown context from AST trace."""
    code = '''def divide_numbers(numerator, denominator):
    # Perform division
    result = numerator / denominator
    return result
'''
    trace = ast_trace_service.trace_error(
        error_file="math_util.py",
        error_line=3,
        repo_path="",
        source_code=code,
    )
    context_str = ast_trace_service.build_ai_context(trace)
    assert "## Error Location" in context_str
    assert "math_util.py" in context_str
    assert "3" in context_str
    assert "divide_numbers" in context_str


# ============================================================================
# 10. AIAnalyzer Offline/Mock Mode Integration
# ============================================================================

@pytest.mark.asyncio
async def test_mock_ai_analyzer_pipeline(ast_trace_service):
    """Test deterministic offline AI analysis and fix proposal generation."""
    analyzer = AIAnalyzer()
    assert analyzer.is_mock is True, "AI Analyzer should operate in mock mode when configured"

    code = '''def get_user_avatar(users, index):
    target = users[index]
    return target['avatar']
'''
    error = DetectedError(
        error_type="IndexError",
        message="list index out of range",
        source_file="user_service.py",
        line_number=2,
    )

    trace = ast_trace_service.trace_error(
        error_file=error.source_file,
        error_line=error.line_number,
        repo_path="",
        source_code=code,
    )
    ast_ctx = ast_trace_service.build_ai_context(trace)

    # 1. Root Cause Analysis
    conversation = []
    analysis = await analyzer.analyze_error(
        error=error,
        source_code=trace.error_context_code,
        ast_context=ast_ctx,
        conversation=conversation,
    )

    assert analysis is not None
    assert analysis.confidence >= 0.85
    assert analysis.error_category == "index_error"
    assert "IndexError" in analysis.root_cause

    # 2. Fix Proposal Generation
    proposals = await analyzer.generate_fix_proposals(
        error=error,
        analysis=analysis,
        source_code=trace.error_context_code,
        ast_context=ast_ctx,
        conversation=conversation,
    )

    assert len(proposals) >= 1
    prop = proposals[0]
    assert prop.target_file == "user_service.py"
    assert prop.line_number == 2
    assert prop.suggested_code != ""
    assert prop.confidence >= 0.85
