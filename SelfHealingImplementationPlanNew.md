System Overview
The system addresses production error detection and code review challenges by integrating repository access for code context, real-time log streaming via WebSocket, AST-based error tracing, and AI-driven analysis for fix suggestions and PR reviews. Users grant read-only repo access and integrate a lightweight WebSocket client to forward logs, enabling the server to pull latest code, build ASTs, and provide contextual AI guidance without executing fixes or tests. This approach leverages agentic AI for root cause analysis from mixed logs and optimizes review processes.
​
​

User Onboarding
Users register by providing read-only GitHub/GitLab repository access tokens, selecting the production base branch (e.g., main), and integrating a small Python/JS WebSocket client snippet into their application for bidirectional log streaming. The client captures stdout/stderr and production logs, forwarding them over WebSocket to the service endpoint, handling reconnections for reliability in production environments behind proxies like Nginx. The service periodically performs git pull on the repo (no write access needed) and caches the latest state.
​

Core Architecture
Deploy on VMs with a backend server (Node.js/Python FastAPI) managing WebSocket connections, repo cloning, and AI orchestration; use PostgreSQL/Redis for session storage and AST caches. Key components include a log processor for real-time parsing, AST builder for codebase analysis, GitHub API integrator for PR diffs, and agentic AI pipeline using frameworks like LangChain or AutoGen for multi-step reasoning. Scale with Docker/Kubernetes for handling multiple users' logs and repos securely.
​

Error Detection Workflow
WebSocket receives mixed production logs; apply pattern matching and AI log analysis (e.g., regex + LLM for anomaly detection) to identify errors, correlating across streams without user-provided filters.
​
​

On error detection, trigger git pull for latest code, then parse entire codebase into AST using Python's ast module or Tree-sitter for multi-language support, focusing on relevant files via stack traces.
​

Replicate error via simulated API call with varied arguments to confirm type; traverse AST to extract error node, parent/child contexts (e.g., function blocks, dependencies), and cross-references.
​

Feed enriched context (logs + AST snippets + line numbers) to agentic AI for root cause analysis and fix proposals; generate detailed email with explanations, code diffs, and risks.
​

Code Review Workflow
Monitor user-specified webhooks or poll GitHub/GitLab API for new PRs on selected repos, fetching three-dot diffs between base branch and PR branch for clean change isolation. AI analyzes diffs: check quality standards, suggest optimizations, flag issues like unused imports or security gaps, mimicking senior reviews without multi-layer human processes. Post threaded comments via API or send notification summaries, supporting iterative feedback loops.
​