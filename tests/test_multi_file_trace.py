"""
Multi-File Python Service Cross-Module AST Traceback Tests
==========================================================
Verifies multi-hop AST tracing, cross-module reference resolution,
call-chain traceback parsing, and AI rich-context building across
multi-file Python architectures.
"""

import os
import sys
import tempfile
from pathlib import Path
import pytest

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.ast_trace_service import ASTTraceService
from services.ai_analyzer import AIAnalyzer
from utils.models import DetectedError, ASTNode
from main import _build_call_chain, _normalize_line_number


@pytest.fixture
def multi_file_service_repo(tmp_path):
    """
    Creates a realistic multi-module Python service repository:
      gateway/
        __init__.py
        checkout_router.py   (Hop 3: Entrypoint / controller)
      services/
        __init__.py
        billing_service.py   (Hop 2: Service layer orchestrator)
      utils/
        __init__.py
        tax_calculator.py    (Hop 1: Core calculation utility)
      models/
        __init__.py
        currency.py          (Hop 0: Leaf model / domain helper)
    """
    repo_dir = tmp_path / "ecommerce_service"
    repo_dir.mkdir()

    # 1. models/currency.py
    models_dir = repo_dir / "models"
    models_dir.mkdir()
    (models_dir / "__init__.py").write_text('"""Models package."""\n')
    (models_dir / "currency.py").write_text('''"""Currency domain models and validation."""

SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP"}

def validate_currency(currency_code: str) -> bool:
    """Verify currency code is active and supported."""
    if not currency_code or not isinstance(currency_code, str):
        return False
    return currency_code.upper() in SUPPORTED_CURRENCIES
''')

    # 2. utils/tax_calculator.py (Contains bug: divisor may be 0)
    utils_dir = repo_dir / "utils"
    utils_dir.mkdir()
    (utils_dir / "__init__.py").write_text('"""Utils package."""\n')
    (utils_dir / "tax_calculator.py").write_text('''"""Sales tax and fee calculator."""
from models.currency import validate_currency

def calculate_sales_tax(subtotal: float, region_code: str, rates: dict) -> float:
    """Compute regional sales tax using rate mapping."""
    if not validate_currency(rates.get("currency", "USD")):
        raise ValueError("Unsupported currency")
    divisor = rates.get(region_code, 0)
    # Line 10: Buggy division when rate divisor is 0
    tax_amount = subtotal / divisor
    return round(tax_amount, 2)
''')

    # 3. services/billing_service.py (Calls utils.tax_calculator)
    services_dir = repo_dir / "services"
    services_dir.mkdir()
    (services_dir / "__init__.py").write_text('"""Services package."""\n')
    (services_dir / "billing_service.py").write_text('''"""Billing and invoice processing."""
from utils.tax_calculator import calculate_sales_tax

def process_invoice(order_id: str, items: list, tax_rates: dict) -> dict:
    """Process order items and calculate totals with tax."""
    subtotal = sum(item.get("price", 0.0) * item.get("qty", 1) for item in items)
    region = tax_rates.get("default_region", "STANDARD")
    tax = calculate_sales_tax(subtotal, region, tax_rates)
    return {
        "order_id": order_id,
        "subtotal": subtotal,
        "tax": tax,
        "total": subtotal + tax,
    }
''')

    # 4. gateway/checkout_router.py (Entry point calling services.billing_service)
    gateway_dir = repo_dir / "gateway"
    gateway_dir.mkdir()
    (gateway_dir / "__init__.py").write_text('"""Gateway router."""\n')
    (gateway_dir / "checkout_router.py").write_text('''"""API checkout router."""
import logging
from services.billing_service import process_invoice

logger = logging.getLogger("checkout")

def handle_checkout(request_data: dict) -> dict:
    """Handle incoming checkout HTTP request payload."""
    order_id = request_data["order_id"]
    items = request_data.get("items", [])
    rates = request_data.get("rates", {})
    return process_invoice(order_id, items, rates)
''')

    # 5. requirements.txt
    (repo_dir / "requirements.txt").write_text("fastapi>=0.109.0\npydantic>=2.5.0\n")

    return repo_dir


# ============================================================================
# 1. Multi-Hop Stack Trace Parsing (_build_call_chain)
# ============================================================================

def test_multi_hop_call_chain_parsing(multi_file_service_repo):
    """
    Verify _build_call_chain parses a multi-hop Python traceback spanning
    gateway -> services -> utils, returning innermost-first frames.
    """
    repo = str(multi_file_service_repo)
    stack_trace = f"""Traceback (most recent call last):
  File "{repo}/gateway/checkout_router.py", line 12, in handle_checkout
    return process_invoice(order_id, items, rates)
  File "{repo}/services/billing_service.py", line 9, in process_invoice
    tax = calculate_sales_tax(subtotal, region, tax_rates)
  File "{repo}/utils/tax_calculator.py", line 10, in calculate_sales_tax
    tax_amount = subtotal / divisor
ZeroDivisionError: division by zero"""

    call_chain = _build_call_chain(stack_trace, repo)
    assert len(call_chain) == 3, f"Expected 3 frames, got {len(call_chain)}"

    # Frame 0 (Innermost crash site)
    assert call_chain[0][0] == "utils/tax_calculator.py"
    assert call_chain[0][1] == 10
    assert call_chain[0][2] == "calculate_sales_tax"

    # Frame 1 (Caller in service layer)
    assert call_chain[1][0] == "services/billing_service.py"
    assert call_chain[1][1] == 9
    assert call_chain[1][2] == "process_invoice"

    # Frame 2 (Outermost handler in gateway router)
    assert call_chain[2][0] == "gateway/checkout_router.py"
    assert call_chain[2][1] == 12
    assert call_chain[2][2] == "handle_checkout"


def test_multi_hop_call_chain_single_quote_traceback(multi_file_service_repo):
    """Verify _build_call_chain handles single-quoted tracebacks as well."""
    repo = str(multi_file_service_repo)
    stack_trace = f"""Traceback (most recent call last):
  File '{repo}/gateway/checkout_router.py', line 12, in handle_checkout
    return process_invoice(order_id, items, rates)
  File '{repo}/services/billing_service.py', line 9, in process_invoice
    tax = calculate_sales_tax(subtotal, region, tax_rates)
  File '{repo}/utils/tax_calculator.py', line 10, in calculate_sales_tax
    tax_amount = subtotal / divisor
ZeroDivisionError: division by zero"""

    call_chain = _build_call_chain(stack_trace, repo)
    assert len(call_chain) == 3
    assert call_chain[0][0] == "utils/tax_calculator.py"
    assert call_chain[1][0] == "services/billing_service.py"
    assert call_chain[2][0] == "gateway/checkout_router.py"


# ============================================================================
# 2. Multi-Hop AST Reference Resolution across Modules
# ============================================================================

def test_multi_hop_ast_reference_traversal(multi_file_service_repo):
    """
    Verify ASTTraceService traverses multi-hop imports:
    gateway/checkout_router.py -> services/billing_service.py -> utils/tax_calculator.py -> models/currency.py
    """
    svc = ASTTraceService()
    repo = str(multi_file_service_repo)

    # Start trace from gateway router with max_hops=3
    trace = svc.trace_error(
        error_file="gateway/checkout_router.py",
        error_line=12,
        repo_path=repo,
        max_hops=3,
    )

    assert trace is not None
    assert trace.main_ast is not None
    assert trace.main_ast.node_type == "module"

    # Check referenced files contain ASTs from downstream modules
    resolved_files = list(trace.referenced_files.keys())
    assert len(resolved_files) >= 2, f"Expected multiple resolved modules, got {resolved_files}"

    # Billing service AST must be parsed
    has_billing = any("billing_service.py" in p for p in resolved_files)
    assert has_billing, "services/billing_service.py AST should be resolved and parsed"

    # Tax calculator AST must be resolved via multi-hop
    has_tax = any("tax_calculator.py" in p for p in resolved_files)
    assert has_tax, "utils/tax_calculator.py AST should be resolved and parsed via multi-hop traversal"

    # Verify each resolved file in referenced_files is a parsed ASTNode
    for p, ast_node in trace.referenced_files.items():
        assert isinstance(ast_node, ASTNode)
        assert ast_node.node_type == "module"
        assert len(ast_node.children) > 0


# ============================================================================
# 3. Rich AI Context Extraction Across Multi-Module Call Chains
# ============================================================================

def test_multi_hop_ai_context_extraction(multi_file_service_repo):
    """
    Verify build_ai_context extracts full function bodies and import contexts
    across all involved modules in a multi-hop call chain.
    """
    svc = ASTTraceService()
    repo = str(multi_file_service_repo)

    # Innermost error in utils/tax_calculator.py at line 10
    trace = svc.trace_error(
        error_file="utils/tax_calculator.py",
        error_line=10,
        repo_path=repo,
        max_hops=2,
    )

    # Attach the 3-frame call chain (innermost first)
    trace.call_chain = [
        ("utils/tax_calculator.py", 10, "calculate_sales_tax"),
        ("services/billing_service.py", 9, "process_invoice"),
        ("gateway/checkout_router.py", 12, "handle_checkout"),
    ]

    context = svc.build_ai_context(trace, repo_path=repo)
    assert context is not None

    # 1. Headline & Call Chain
    assert "## Error Location" in context
    assert "utils/tax_calculator.py" in context
    assert "Line: 10" in context
    assert "## Call Chain" in context
    assert "→ `utils/tax_calculator.py:10` in `calculate_sales_tax`" in context
    assert "`services/billing_service.py:9` in `process_invoice`" in context
    assert "`gateway/checkout_router.py:12` in `handle_checkout`" in context

    # 2. Full function bodies extracted for all 3 frames
    assert "calculate_sales_tax" in trace.traced_functions.get("utils/tax_calculator.py:calculate_sales_tax", "")
    assert "process_invoice" in trace.traced_functions.get("services/billing_service.py:process_invoice", "")
    assert "handle_checkout" in trace.traced_functions.get("gateway/checkout_router.py:handle_checkout", "")

    # 3. Import context for all involved files
    assert "## Import Context" in context
    assert "`utils/tax_calculator.py` imports:" in context
    assert "from models.currency import validate_currency" in context
    assert "`services/billing_service.py` imports:" in context
    assert "from utils.tax_calculator import calculate_sales_tax" in context
    assert "`gateway/checkout_router.py` imports:" in context
    assert "from services.billing_service import process_invoice" in context


# ============================================================================
# 4. Cross-Module ImportError Traceback Verification
# ============================================================================

def test_cross_module_import_error_traceback(tmp_path):
    """
    Verify AST trace and AI diagnosis on a multi-module service with a broken import:
    api/routes.py -> services/inventory.py (ImportError: cannot import name 'reserve_stock')
    """
    repo = tmp_path / "broken_service"
    repo.mkdir()

    # services/inventory.py - missing reserve_stock (only has check_stock)
    services_dir = repo / "services"
    services_dir.mkdir()
    (services_dir / "__init__.py").write_text("")
    (services_dir / "inventory.py").write_text('''"""Inventory service."""

def check_stock(item_id: str) -> int:
    """Check current available quantity."""
    return 42
''')

    # api/routes.py - attempts to import non-existent reserve_stock
    api_dir = repo / "api"
    api_dir.mkdir()
    (api_dir / "__init__.py").write_text("")
    routes_code = '''"""API routes."""
from services.inventory import reserve_stock

def place_order(order_data: dict):
    return reserve_stock(order_data["item_id"])
'''
    (api_dir / "routes.py").write_text(routes_code)

    svc = ASTTraceService()
    trace = svc.trace_error(
        error_file="api/routes.py",
        error_line=2,
        repo_path=str(repo),
        max_hops=2,
    )

    assert trace is not None
    assert trace.error_file == "api/routes.py"
    assert trace.error_line == 2
    assert ">>>    2 | from services.inventory import reserve_stock" in trace.error_context_code

    # References should capture the import to services/inventory
    refs = [r for r in trace.references if "inventory" in r.to_file]
    assert len(refs) >= 1
    assert refs[0].symbol_name == "reserve_stock"
    assert refs[0].resolved_path is not None
    assert "inventory.py" in refs[0].resolved_path

    # Referenced AST should contain the parsed target module
    assert refs[0].resolved_path in trace.referenced_files
    target_ast = trace.referenced_files[refs[0].resolved_path]
    func_names = [c.name for c in target_ast.children if "function" in c.node_type]
    assert "check_stock" in func_names
    assert "reserve_stock" not in func_names, "reserve_stock should be missing from target file"


# ============================================================================
# 5. End-to-End AI Analysis & Fix Proposal on Multi-Hop Failure
# ============================================================================

@pytest.mark.asyncio
async def test_multi_hop_ai_analysis_and_fix(multi_file_service_repo):
    """
    Verify AIAnalyzer operates on rich multi-hop AST context and synthesizes
    a targeted defensive fix proposal on the root-cause file.
    """
    svc = ASTTraceService()
    analyzer = AIAnalyzer()
    repo = str(multi_file_service_repo)

    error = DetectedError(
        error_type="ZeroDivisionError",
        message="division by zero",
        source_file="utils/tax_calculator.py",
        line_number=10,
        stack_trace=f"""Traceback (most recent call last):
  File "{repo}/gateway/checkout_router.py", line 12, in handle_checkout
    return process_invoice(order_id, items, rates)
  File "{repo}/services/billing_service.py", line 9, in process_invoice
    tax = calculate_sales_tax(subtotal, region, tax_rates)
  File "{repo}/utils/tax_calculator.py", line 10, in calculate_sales_tax
    tax_amount = subtotal / divisor
ZeroDivisionError: division by zero""",
    )

    trace = svc.trace_error(
        error_file=error.source_file,
        error_line=error.line_number,
        repo_path=repo,
        max_hops=2,
    )
    trace.call_chain = [
        ("utils/tax_calculator.py", 10, "calculate_sales_tax"),
        ("services/billing_service.py", 9, "process_invoice"),
        ("gateway/checkout_router.py", 12, "handle_checkout"),
    ]
    ast_ctx = svc.build_ai_context(trace, repo_path=repo)

    # 1. Root Cause Analysis
    conversation = []
    analysis = await analyzer.analyze_error(
        error=error,
        source_code=trace.error_context_code,
        ast_context=ast_ctx,
        conversation=conversation,
        repo_path=repo,
        user_id="ecommerce-test",
    )

    assert analysis.confidence >= 0.85
    assert analysis.error_category in ("logic_error", "zero_division", "calculation_error")
    assert "ZeroDivisionError" in analysis.root_cause

    # 2. Fix Proposal
    proposals = await analyzer.generate_fix_proposals(
        error=error,
        analysis=analysis,
        source_code=trace.error_context_code,
        ast_context=ast_ctx,
        conversation=conversation,
        repo_path=repo,
        user_id="ecommerce-test",
    )

    assert len(proposals) >= 1
    p = proposals[0]
    assert p.target_file == "utils/tax_calculator.py"
    assert p.line_number == 10
    assert p.suggested_code != ""
    assert "divisor != 0" in p.suggested_code or "if divisor" in p.suggested_code
    assert p.confidence >= 0.85
