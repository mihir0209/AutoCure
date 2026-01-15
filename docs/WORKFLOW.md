# Self-Healing Software System - Workflow Algorithm

## Overview

This document describes the complete workflow algorithm implemented in the Self-Healing Software System.

## Algorithm Flowchart

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              START                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MAIN ORCHESTRATOR (Python)                               │
│                    Initialize all components                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
        ┌───────────────────┐           ┌───────────────────┐
        │   SUBPROCESS 1    │           │   SUBPROCESS 2    │
        │   Log Watcher     │◄──────────│  Target Service   │
        │                   │   logs    │   (Node.js)       │
        │ • Monitor logs    │           │                   │
        │ • Detect errors   │           │ • Run application │
        │ • Parse traces    │           │ • Generate logs   │
        └─────────┬─────────┘           └───────────────────┘
                  │
                  │ Error detected?
                  │
          ┌───────┴───────┐
          │               │
          ▼               ▼
    ┌──────────┐    ┌──────────┐
    │   NO     │    │   YES    │
    │          │    │          │
    │ Continue │    │ Process  │
    │ watching │    │ error    │
    └────┬─────┘    └────┬─────┘
         │               │
         │               ▼
         │     ┌───────────────────┐
         │     │   SUBPROCESS 3    │
         │     │  Error Processor  │
         │     │                   │
         │     │ • Parse stack     │
         │     │ • Trace origin    │
         │     │ • Get context     │
         │     │ • Analyze root    │
         │     │   cause           │
         │     └─────────┬─────────┘
         │               │
         │               ▼
         │     ┌───────────────────────────────────────────┐
         │     │            AI HEALING AGENT               │
         │     │                                           │
         │     │  ┌─────────────────────────────────────┐ │
         │     │  │        AI CLIENT                    │ │
         │     │  │   (Groq / Cerebras)                 │ │
         │     │  │                                     │ │
         │     │  │  • Generate fix proposal            │ │
         │     │  │  • Generate test cases              │ │
         │     │  └─────────────────────────────────────┘ │
         │     └─────────────────┬─────────────────────────┘
         │                       │
         │                       ▼
         │     ┌─────────────────────────────────────────────────────────────┐
         │     │                 FIX PROPOSAL EXECUTION LOOP                 │
         │     │                                                             │
         │     │   ┌─────────────────────────────────────────────────────┐  │
         │     │   │  For attempt = 1 to MAX_ATTEMPTS:                   │  │
         │     │   │                                                     │  │
         │     │   │    1. Generate/Improve Fix                         │  │
         │     │   │       └─► AI generates fixed code                  │  │
         │     │   │                                                     │  │
         │     │   │    2. Generate Tests                               │  │
         │     │   │       └─► AI creates test cases                    │  │
         │     │   │                                                     │  │
         │     │   │    3. Run Tests in Sandbox                         │  │
         │     │   │       └─► Execute in temp directory                │  │
         │     │   │                                                     │  │
         │     │   │    4. Check Results                                │  │
         │     │   │       │                                            │  │
         │     │   │       ├─► PASS ──► Exit loop (success)            │  │
         │     │   │       │                                            │  │
         │     │   │       └─► FAIL ──► Continue to next attempt       │  │
         │     │   │                     │                              │  │
         │     │   │                     └─► AI analyzes failure       │  │
         │     │   │                         and improves fix          │  │
         │     │   │                                                     │  │
         │     │   └─────────────────────────────────────────────────────┘  │
         │     │                                                             │
         │     └──────────────────────────┬──────────────────────────────────┘
         │                                │
         │                    ┌───────────┴───────────┐
         │                    │                       │
         │                    ▼                       ▼
         │           ┌──────────────┐       ┌──────────────┐
         │           │   SUCCESS    │       │   FAILED     │
         │           │              │       │              │
         │           │ Tests passed │       │ Max attempts │
         │           │              │       │ reached      │
         │           └──────┬───────┘       └──────┬───────┘
         │                  │                      │
         │                  ▼                      │
         │     ┌───────────────────┐               │
         │     │   SUBPROCESS 4    │               │
         │     │   Git Handler     │               │
         │     │                   │               │
         │     │ • Create branch   │               │
         │     │ • Apply fix       │               │
         │     │ • Commit changes  │               │
         │     │ • (Optional push) │               │
         │     └─────────┬─────────┘               │
         │               │                         │
         │               └─────────┬───────────────┘
         │                         │
         │                         ▼
         │           ┌───────────────────┐
         │           │  EMAIL NOTIFIER   │
         │           │                   │
         │           │ • Create report   │
         │           │ • Format HTML     │
         │           │ • Send via SMTP   │
         │           │ • Include:        │
         │           │   - Error details │
         │           │   - Fix proposal  │
         │           │   - Test results  │
         │           │   - Git branch    │
         │           │   - Severity      │
         │           └─────────┬─────────┘
         │                     │
         │                     ▼
         │           ┌───────────────────┐
         │           │   HEALING REPORT  │
         │           │      LOGGED       │
         │           └─────────┬─────────┘
         │                     │
         └─────────────────────┘
                    │
                    ▼
            [Continue Monitoring]
```

## Detailed Process Flow

### Phase 1: Initialization

```python
# Main orchestrator startup sequence
1. Load configuration from environment
2. Initialize Log Watcher (subprocess1)
3. Initialize Error Processor (subprocess3)
4. Initialize Healing Agent
5. Initialize Git Handler (subprocess4)
6. Initialize Email Notifier
7. Start target service (subprocess2)
8. Begin monitoring loop
```

### Phase 2: Error Detection (Subprocess 1)

```python
# Log Watcher algorithm
while running:
    1. Check for new log entries
    2. For each new line:
       a. Match against error patterns
       b. If error detected:
          - Parse stack trace
          - Extract source file and line
          - Determine severity
          - Create ErrorInfo object
          - Yield to orchestrator
    3. Sleep for watch_interval
```

### Phase 3: Error Processing (Subprocess 3)

```python
# Error Processor algorithm
def trace_error_origin(error_info):
    1. Extract related files from stack trace
    2. Resolve source file path
    3. Read code context (N lines before/after)
    4. Perform root cause analysis:
       - Check error type patterns
       - Analyze error message
       - Identify common issues
    5. Return enriched ErrorInfo
```

### Phase 4: AI Healing (Healing Agent)

```python
# Healing Agent algorithm
def heal(error_info):
    report = new HealingReport()
    source_code = read_source_file()
    
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Step 1: Generate or improve fix
        if attempt == 1:
            fix_result = ai_client.generate_fix(
                error_context=format_error_context(error_info),
                source_code=source_code
            )
        else:
            fix_result = ai_client.analyze_test_failure(
                test_output=last_test_result.output,
                source_code=current_code,
                previous_explanation=previous_fix.explanation
            )
        
        # Step 2: Create fix proposal
        fix_proposal = create_fix_proposal(fix_result, attempt)
        report.fix_proposals.append(fix_proposal)
        
        # Step 3: Generate tests
        test_code = ai_client.generate_tests(
            source_code=fix_proposal.fixed_code,
            error_type=error_info.error_type
        )
        
        # Step 4: Run tests in sandbox
        test_result = run_tests_in_sandbox(fix_proposal, test_code)
        report.test_results.append(test_result)
        
        # Step 5: Check results
        if test_result.passed:
            fix_proposal.status = PASSED
            report.final_fix = fix_proposal
            break
        else:
            fix_proposal.status = FAILED
            current_code = fix_proposal.fixed_code  # Base for next attempt
    
    return report
```

### Phase 5: Git Operations (Subprocess 4)

```python
# Git Handler algorithm
def create_fix_branch(fix, error_info):
    1. Generate unique branch name:
       branch = f"ai-fix/{error_type}-{timestamp}-{fix_id}"
    
    2. Save current branch
    3. Create and checkout new branch
    4. Apply fix to target file
    5. Stage changes (git add)
    6. Create descriptive commit message
    7. Commit changes
    8. Get commit hash
    9. Return to original branch
    10. Return (branch_name, commit_hash)
```

### Phase 6: Notification (Email Notifier)

```python
# Email Notifier algorithm
def send_healing_report(report):
    1. Create subject line with status and severity
    2. Generate HTML report:
       - Header with status badge
       - Error details section
       - Root cause analysis
       - Stack trace
       - Test results table
       - Fix details (if successful)
       - Git information
    3. Generate plain text fallback
    4. Connect to SMTP server with TLS
    5. Authenticate with app password
    6. Send email
```

## State Transitions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FIX PROPOSAL STATES                                 │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────┐                 ┌─────────┐
    │ PENDING │ ───Generate───▶ │ TESTING │
    └─────────┘                 └────┬────┘
                                     │
                           ┌─────────┴─────────┐
                           │                   │
                           ▼                   ▼
                    ┌──────────┐         ┌──────────┐
                    │  PASSED  │         │  FAILED  │
                    └────┬─────┘         └────┬─────┘
                         │                    │
                         ▼                    ▼
                    ┌──────────┐         [Next Attempt]
                    │ APPLIED  │              or
                    └──────────┘         [Max Reached]
```

## Error Severity Classification

| Severity | Conditions | Actions |
|----------|-----------|---------|
| LOW | Warnings, deprecation notices | Log and monitor |
| MEDIUM | Runtime errors, handled exceptions | Normal healing flow |
| HIGH | TypeError, ReferenceError | Priority healing |
| CRITICAL | Fatal errors, unhandled exceptions | Immediate alert + healing |

## Test Execution Sandbox

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        TEST SANDBOX ENVIRONMENT                             │
└─────────────────────────────────────────────────────────────────────────────┘

    Original Service Directory          Temporary Test Directory
    ┌─────────────────────┐             ┌─────────────────────┐
    │ demo_service/       │   Copy      │ /tmp/selfhealer_*/  │
    │ ├── server.js       │ ─────────▶  │ ├── server.js       │ ◄─ Fixed
    │ ├── package.json    │             │ ├── package.json    │
    │ └── tests/          │             │ └── tests/          │
    │     └── *.test.js   │             │     └── fix_test.js │ ◄─ Generated
    └─────────────────────┘             └─────────────────────┘
                                                   │
                                                   ▼
                                        ┌─────────────────────┐
                                        │   node --test       │
                                        │   tests/fix_test.js │
                                        └─────────────────────┘
                                                   │
                                                   ▼
                                        ┌─────────────────────┐
                                        │   Parse Results     │
                                        │   Cleanup Temp Dir  │
                                        └─────────────────────┘
```

## Performance Considerations

1. **Log Watching**: Uses file position tracking to read only new content
2. **AI Calls**: Includes retry logic and timeout handling
3. **Test Execution**: Runs in isolated temp directories with timeout
4. **Memory**: Cleans up temporary files after each test run
5. **Concurrency**: Main loop is async for non-blocking I/O

## Failure Handling

| Failure Type | Handling Strategy |
|--------------|-------------------|
| AI API timeout | Retry up to 3 times |
| AI API error | Log error, continue to next attempt |
| Test timeout | Kill process, mark as failed |
| Git error | Log error, skip branch creation |
| Email error | Log error, continue execution |
| Source file not found | Skip healing, log warning |
