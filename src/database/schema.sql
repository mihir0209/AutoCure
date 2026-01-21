-- Self-Healing Software System v2.0 - PostgreSQL Schema
-- Run this script to initialize the database

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- USERS TABLE
-- ============================================================================
-- Stores user account information
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,  -- bcrypt hashed
    name VARCHAR(255),
    
    -- Subscription tier: 'free' or 'pro'
    tier VARCHAR(20) DEFAULT 'free' CHECK (tier IN ('free', 'pro')),
    
    -- Free: 5 repos max, Pro: unlimited
    max_repos INTEGER DEFAULT 5,
    
    -- Free: 100MB/repo, Pro: 1GB/repo
    max_storage_per_repo_mb INTEGER DEFAULT 100,
    
    -- JWT token for WebSocket authentication
    websocket_token VARCHAR(512),
    
    -- Email notification preferences
    notifications_enabled BOOLEAN DEFAULT TRUE,
    
    -- Account status
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE
);

-- Index for email lookups
CREATE INDEX idx_users_email ON users(email);

-- ============================================================================
-- REPOSITORIES TABLE
-- ============================================================================
-- Stores repository information (one user can have multiple repos)
CREATE TABLE repositories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Repository information
    repo_url VARCHAR(512) NOT NULL,
    repo_name VARCHAR(255) NOT NULL,
    repo_owner VARCHAR(255) NOT NULL,
    
    -- Git configuration
    base_branch VARCHAR(100) DEFAULT 'main',
    github_token_encrypted BYTEA,  -- Encrypted with pgcrypto
    
    -- Local workspace path
    workspace_path VARCHAR(512),
    
    -- Storage tracking
    current_storage_mb DECIMAL(10, 2) DEFAULT 0,
    
    -- Last sync information
    last_commit_hash VARCHAR(64),
    last_sync_at TIMESTAMP WITH TIME ZONE,
    sync_status VARCHAR(50) DEFAULT 'pending' CHECK (sync_status IN ('pending', 'syncing', 'synced', 'error')),
    sync_error_message TEXT,
    
    -- Monitoring status
    is_monitoring_active BOOLEAN DEFAULT TRUE,
    
    -- Admin email for this repo (can be different from user email)
    admin_email VARCHAR(255),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Unique constraint: one user can't add same repo twice
    UNIQUE(user_id, repo_url)
);

-- Indexes
CREATE INDEX idx_repositories_user_id ON repositories(user_id);
CREATE INDEX idx_repositories_repo_url ON repositories(repo_url);
CREATE INDEX idx_repositories_sync_status ON repositories(sync_status);

-- ============================================================================
-- ERROR LOGS TABLE
-- ============================================================================
-- Stores detected errors from WebSocket log streams
CREATE TABLE error_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repo_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    
    -- Error information
    error_type VARCHAR(100),  -- e.g., 'TypeError', 'ValueError', 'HTTPError'
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    
    -- Source information
    file_path VARCHAR(512),
    line_number INTEGER,
    function_name VARCHAR(255),
    
    -- API endpoint if applicable
    api_endpoint VARCHAR(512),
    http_method VARCHAR(10),
    request_payload JSONB,
    
    -- Log context
    log_level VARCHAR(20),  -- ERROR, CRITICAL, etc.
    raw_log_entry TEXT,
    
    -- Severity assessment
    severity VARCHAR(20) DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    
    -- Processing status
    status VARCHAR(50) DEFAULT 'detected' CHECK (status IN ('detected', 'analyzing', 'analyzed', 'notified', 'resolved', 'ignored')),
    
    -- Timestamps
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- Indexes
CREATE INDEX idx_error_logs_repo_id ON error_logs(repo_id);
CREATE INDEX idx_error_logs_status ON error_logs(status);
CREATE INDEX idx_error_logs_occurred_at ON error_logs(occurred_at DESC);
CREATE INDEX idx_error_logs_severity ON error_logs(severity);

-- ============================================================================
-- ANALYSIS HISTORY TABLE
-- ============================================================================
-- Stores AI analysis results and fix proposals
CREATE TABLE analysis_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    error_log_id UUID NOT NULL REFERENCES error_logs(id) ON DELETE CASCADE,
    repo_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    
    -- Analysis results
    root_cause TEXT,
    root_cause_confidence DECIMAL(3, 2),  -- 0.00 to 1.00
    
    -- Fix proposal
    fix_proposal TEXT,
    fix_diff TEXT,  -- Unified diff format
    affected_files JSONB,  -- Array of file paths
    
    -- Risk assessment
    risk_level VARCHAR(20) CHECK (risk_level IN ('low', 'medium', 'high')),
    risk_explanation TEXT,
    
    -- AI provider information
    ai_provider VARCHAR(50),  -- 'groq' or 'cerebras'
    ai_model VARCHAR(100),
    tokens_used INTEGER,
    analysis_duration_ms INTEGER,
    
    -- AST context used
    ast_context JSONB,  -- Serialized AST nodes
    
    -- Email notification
    email_sent BOOLEAN DEFAULT FALSE,
    email_sent_at TIMESTAMP WITH TIME ZONE,
    email_recipient VARCHAR(255),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_analysis_history_error_log_id ON analysis_history(error_log_id);
CREATE INDEX idx_analysis_history_repo_id ON analysis_history(repo_id);
CREATE INDEX idx_analysis_history_created_at ON analysis_history(created_at DESC);

-- ============================================================================
-- CODE REVIEWS TABLE
-- ============================================================================
-- Stores PR code review results
CREATE TABLE code_reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repo_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    
    -- PR information
    pr_number INTEGER NOT NULL,
    pr_title VARCHAR(512),
    pr_url VARCHAR(512),
    pr_author VARCHAR(255),
    base_branch VARCHAR(100),
    head_branch VARCHAR(100),
    
    -- Review results
    overall_score INTEGER CHECK (overall_score >= 0 AND overall_score <= 100),
    summary TEXT,
    comments JSONB,  -- Array of review comments
    
    -- Categories
    has_security_issues BOOLEAN DEFAULT FALSE,
    has_performance_issues BOOLEAN DEFAULT FALSE,
    has_style_issues BOOLEAN DEFAULT FALSE,
    
    -- AI provider information
    ai_provider VARCHAR(50),
    ai_model VARCHAR(100),
    tokens_used INTEGER,
    
    -- Email notification
    email_sent BOOLEAN DEFAULT FALSE,
    email_sent_at TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    reviewed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_code_reviews_repo_id ON code_reviews(repo_id);
CREATE INDEX idx_code_reviews_pr_number ON code_reviews(repo_id, pr_number);

-- ============================================================================
-- WEBSOCKET SESSIONS TABLE
-- ============================================================================
-- Tracks active WebSocket connections (also mirrored in Redis for speed)
CREATE TABLE websocket_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    repo_id UUID REFERENCES repositories(id) ON DELETE SET NULL,
    
    -- Connection info
    connection_id VARCHAR(255) UNIQUE NOT NULL,
    client_ip VARCHAR(45),
    user_agent TEXT,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_heartbeat_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    disconnected_at TIMESTAMP WITH TIME ZONE
);

-- Indexes
CREATE INDEX idx_websocket_sessions_user_id ON websocket_sessions(user_id);
CREATE INDEX idx_websocket_sessions_connection_id ON websocket_sessions(connection_id);
CREATE INDEX idx_websocket_sessions_is_active ON websocket_sessions(is_active);

-- ============================================================================
-- RATE LIMITS TABLE
-- ============================================================================
-- Persistent rate limit tracking (Redis for real-time, Postgres for history)
CREATE TABLE rate_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Rate limit type
    limit_type VARCHAR(50) NOT NULL,  -- 'logs_per_sec', 'prs_per_hour', 'api_calls'
    
    -- Current usage
    current_count INTEGER DEFAULT 0,
    max_count INTEGER NOT NULL,
    
    -- Window
    window_start TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    window_duration_seconds INTEGER NOT NULL,
    
    -- Timestamps
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_rate_limits_user_id ON rate_limits(user_id);
CREATE INDEX idx_rate_limits_type ON rate_limits(limit_type);

-- ============================================================================
-- AUDIT LOG TABLE
-- ============================================================================
-- Security audit trail
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- Action information
    action VARCHAR(100) NOT NULL,  -- 'login', 'repo_added', 'token_updated', etc.
    resource_type VARCHAR(50),  -- 'user', 'repository', 'analysis'
    resource_id UUID,
    
    -- Details
    details JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    
    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);

-- ============================================================================
-- FUNCTIONS AND TRIGGERS
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to relevant tables
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_repositories_updated_at
    BEFORE UPDATE ON repositories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to check repo count for free users
CREATE OR REPLACE FUNCTION check_repo_limit()
RETURNS TRIGGER AS $$
DECLARE
    current_count INTEGER;
    max_repos INTEGER;
BEGIN
    SELECT COUNT(*) INTO current_count FROM repositories WHERE user_id = NEW.user_id;
    SELECT u.max_repos INTO max_repos FROM users u WHERE u.id = NEW.user_id;
    
    IF current_count >= max_repos THEN
        RAISE EXCEPTION 'Repository limit reached. Maximum allowed: %', max_repos;
    END IF;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER check_repo_limit_trigger
    BEFORE INSERT ON repositories
    FOR EACH ROW
    EXECUTE FUNCTION check_repo_limit();

-- ============================================================================
-- INITIAL DATA (Optional)
-- ============================================================================
-- You can add default admin user or test data here

-- Example: Create admin user (uncomment and modify as needed)
-- INSERT INTO users (email, password_hash, name, tier, max_repos, max_storage_per_repo_mb)
-- VALUES ('admin@selfhealer.com', crypt('admin_password', gen_salt('bf')), 'Admin', 'pro', 999999, 10240);
