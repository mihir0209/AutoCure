"""
GitHub Service for the Self-Healing Software System v2.0

Handles all GitHub/GitLab repository operations:
- Cloning repositories with read-only access
- Periodic git pull to keep repos up-to-date
- Fetching PR diffs using three-dot diff method
- Extracting file contents for analysis
"""

import os
import subprocess
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime
import aiohttp

from utils.models import RepositoryInfo, PRInfo, UserRegistration
from utils.logger import setup_colored_logger


logger = setup_colored_logger("github_service")


class GitHubService:
    """
    Service for interacting with GitHub/GitLab repositories.
    
    Features:
    - Clone repositories using HTTPS with token auth
    - Git pull on schedule
    - Fetch PR diffs using GitHub API
    - List files and read contents
    """
    
    def __init__(self, repos_base_path: Path, default_token: Optional[str] = None):
        """
        Initialize the GitHub service.
        
        Args:
            repos_base_path: Base directory for cloned repositories
            default_token: Default GitHub token for API calls
        """
        self.repos_base_path = repos_base_path
        self.default_token = default_token
        
        # Ensure base path exists
        self.repos_base_path.mkdir(parents=True, exist_ok=True)
        
        # Track cloned repos
        self.repos: Dict[str, RepositoryInfo] = {}
        
    def _get_repo_path(self, user_id: str, repo_name: str) -> Path:
        """Get the local path for a user's repository."""
        # Sanitize repo name
        safe_name = repo_name.replace("/", "_").replace("\\", "_")
        return self.repos_base_path / user_id / safe_name
    
    def _parse_repo_url(self, repo_url: str) -> Tuple[str, str, str]:
        """
        Parse repository URL to extract host, owner, and repo name.
        
        Returns: (host, owner, repo_name)
        """
        # Handle HTTPS URLs
        # https://github.com/owner/repo.git
        # https://gitlab.com/owner/repo.git
        
        url = repo_url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]
        
        if "github.com" in url:
            parts = url.split("github.com/")[-1].split("/")
            return "github.com", parts[0], parts[1] if len(parts) > 1 else ""
        elif "gitlab.com" in url:
            parts = url.split("gitlab.com/")[-1].split("/")
            return "gitlab.com", parts[0], parts[1] if len(parts) > 1 else ""
        else:
            # Generic parsing
            parts = url.split("/")
            return parts[-3] if len(parts) > 2 else "", parts[-2] if len(parts) > 1 else "", parts[-1]
    
    async def clone_repository(
        self, user: UserRegistration, force: bool = False
    ) -> Optional[RepositoryInfo]:
        """
        Clone a repository for a user.
        
        Args:
            user: User registration with repo URL and token
            force: If True, remove existing repo and re-clone
            
        Returns:
            RepositoryInfo or None if clone fails
        """
        host, owner, repo_name = self._parse_repo_url(user.repo_url)
        local_path = self._get_repo_path(user.user_id, f"{owner}_{repo_name}")
        
        # Check if already cloned
        if local_path.exists() and not force:
            logger.info(f"Repository already exists: {local_path}")
            repo_info = await self.get_repo_info(user.user_id, local_path)
            if repo_info:
                self.repos[user.user_id] = repo_info
            return repo_info
        
        # Remove existing if force
        if local_path.exists() and force:
            import shutil
            shutil.rmtree(local_path)
        
        # Build clone URL with token
        token = user.access_token or user.repo_token or self.default_token
        if token:
            if "github.com" in user.repo_url:
                clone_url = user.repo_url.replace(
                    "https://", f"https://x-access-token:{token}@"
                )
            else:
                clone_url = user.repo_url.replace(
                    "https://", f"https://oauth2:{token}@"
                )
        else:
            clone_url = user.repo_url
        
        # Create parent directory
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Clone the repository
            logger.info(f"Cloning repository: {user.repo_url} -> {local_path}")
            
            import subprocess as _sp
            try:
                # Use subprocess.run for cross-platform reliability (async subprocess
                # can fail in background tasks on Windows)
                proc = _sp.run(
                    ["git", "clone", "--depth", "1", "-b", user.base_branch,
                     clone_url, str(local_path)],
                    capture_output=True, text=True, timeout=120,
                )
                if proc.returncode != 0:
                    logger.error(f"Git clone failed: {proc.stderr}")
                    return None
            except _sp.TimeoutExpired:
                logger.error("Git clone timed out after 120s")
                return None
            
            logger.info(f"✓ Repository cloned successfully: {local_path}")
            
            # Get repo info
            repo_info = await self.get_repo_info(user.user_id, local_path)
            if repo_info:
                self.repos[user.user_id] = repo_info
            
            return repo_info
            
        except Exception as e:
            logger.error(f"Error cloning repository: {e}")
            return None
    
    async def pull_repository(self, user_id: str, token: str = "") -> bool:
        """
        Pull latest changes for a user's repository.
        
        Args:
            token: Optional PAT token for authenticated pull (private repos).
        
        Returns True if successful, False otherwise.
        """
        repo_info = self.repos.get(user_id)
        if not repo_info:
            logger.warning(f"No repository found for user: {user_id}")
            return False
        
        try:
            import subprocess as _sp
            cwd = str(repo_info.local_path)

            # ── Ensure clean working tree before pulling ──
            # Fix-branch operations may leave uncommitted changes that block rebase.
            # These repos are remote mirrors — local edits are never intentional.
            _sp.run(["git", "reset", "--hard", "HEAD"],
                    cwd=cwd, capture_output=True, text=True, timeout=15)
            _sp.run(["git", "clean", "-fd"],
                    cwd=cwd, capture_output=True, text=True, timeout=15)

            # Unshallow if needed (repos cloned with --depth 1)
            is_shallow = _sp.run(
                ["git", "rev-parse", "--is-shallow-repository"],
                cwd=cwd, capture_output=True, text=True, timeout=15,
            )
            if is_shallow.stdout.strip() == "true":
                logger.info(f"Unshallowing repo for {user_id}...")
                # Inject token for fetch auth if available
                if token:
                    remote_proc = _sp.run(
                        ["git", "remote", "get-url", "origin"],
                        cwd=cwd, capture_output=True, text=True, timeout=15,
                    )
                    original_url = remote_proc.stdout.strip()
                    auth_url = self._inject_token_in_url(original_url, token)
                    _sp.run(["git", "remote", "set-url", "origin", auth_url],
                            cwd=cwd, capture_output=True, text=True, timeout=15)

                _sp.run(["git", "fetch", "--unshallow"],
                        cwd=cwd, capture_output=True, text=True, timeout=120)

                # Restore URL
                if token:
                    self._strip_token_from_remote(cwd)

            # Inject token for pull auth if available
            if token:
                remote_proc = _sp.run(
                    ["git", "remote", "get-url", "origin"],
                    cwd=cwd, capture_output=True, text=True, timeout=15,
                )
                original_url = remote_proc.stdout.strip()
                auth_url = self._inject_token_in_url(original_url, token)
                _sp.run(["git", "remote", "set-url", "origin", auth_url],
                        cwd=cwd, capture_output=True, text=True, timeout=15)

            proc = _sp.run(
                ["git", "pull", "--rebase"],
                cwd=cwd,
                capture_output=True, text=True, timeout=60,
            )

            # Restore URL (strip token)
            if token:
                self._strip_token_from_remote(cwd)
            
            if proc.returncode != 0:
                logger.error(f"Git pull failed: {proc.stderr}")
                return False
            
            # Update repo info
            repo_info.last_pulled = datetime.utcnow()
            repo_info.latest_commit = self._get_latest_commit_sync(Path(repo_info.local_path))
            
            logger.info(f"✓ Repository pulled: {repo_info.local_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error pulling repository: {e}")
            return False

    def _inject_token_in_url(self, url: str, token: str) -> str:
        """Inject a PAT token into a git remote URL for authenticated operations."""
        for prefix in ("https://", "http://"):
            if url.startswith(prefix):
                after = url[len(prefix):]
                if "@" in after.split("/")[0]:
                    after = after.split("@", 1)[1]
                return f"{prefix}x-access-token:{token}@{after}"
        return url

    def _strip_token_from_remote(self, cwd: str):
        """Remove token from the git remote URL for security."""
        import subprocess as _sp
        remote_proc = _sp.run(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd, capture_output=True, text=True, timeout=15,
        )
        current = remote_proc.stdout.strip()
        if "@" in current:
            proto = "https://" if current.startswith("https://") else "http://"
            after_at = current.split("@", 1)[1] if "@" in current else current
            _sp.run(
                ["git", "remote", "set-url", "origin", f"{proto}{after_at}"],
                cwd=cwd, capture_output=True, text=True, timeout=15,
            )
    
    async def get_repo_info(self, user_id: str, local_path: Path) -> Optional[RepositoryInfo]:
        """Get information about a cloned repository."""
        
        if not local_path.exists():
            return None
        
        try:
            import subprocess as _sp
            # Get current branch
            branch_proc = _sp.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(local_path),
                capture_output=True, text=True, timeout=15,
            )
            current_branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else "unknown"
            
            # Get latest commit
            latest_commit = self._get_latest_commit_sync(local_path)
            
            return RepositoryInfo(
                user_id=user_id,
                local_path=str(local_path),
                current_branch=current_branch,
                latest_commit=latest_commit,
                last_pulled=datetime.utcnow(),
            )
            
        except Exception as e:
            logger.error(f"Error getting repo info: {e}", exc_info=True)
            return None
    
    def _get_latest_commit_sync(self, local_path: Path) -> str:
        """Get the latest commit hash (sync for Windows compatibility)."""
        try:
            import subprocess as _sp
            proc = _sp.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(local_path),
                capture_output=True, text=True, timeout=15,
            )
            return proc.stdout.strip() if proc.returncode == 0 else "unknown"
        except Exception:
            return "unknown"
    
    async def get_pr_diff(
        self, user: UserRegistration, pr_number: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get the diff for a pull request using the three-dot diff method.
        
        The three-dot diff shows changes in the PR branch since it diverged
        from the base branch, which is more useful for code review.
        """
        host, owner, repo_name = self._parse_repo_url(user.repo_url)
        token = user.access_token or user.repo_token or self.default_token
        
        if not token:
            logger.error("No token available for API calls")
            return None
        
        if "github.com" in host:
            return await self._get_github_pr_diff(owner, repo_name, pr_number, token)
        else:
            logger.warning(f"PR diff not implemented for: {host}")
            return None
    
    async def _get_github_pr_diff(
        self, owner: str, repo: str, pr_number: int, token: str
    ) -> Optional[Dict[str, Any]]:
        """Get PR diff from GitHub API."""
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3.diff",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                # Get PR info first
                pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
                
                async with session.get(pr_url, headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json",
                }) as response:
                    if response.status != 200:
                        logger.error(f"Failed to get PR info: {response.status}")
                        return None
                    pr_data = await response.json()
                
                # Get the diff
                async with session.get(pr_url, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Failed to get PR diff: {response.status}")
                        return None
                    diff_text = await response.text()
                
                # Get files changed
                files_url = f"{pr_url}/files"
                async with session.get(files_url, headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json",
                }) as response:
                    if response.status != 200:
                        files_data = []
                    else:
                        files_data = await response.json()
                
                return {
                    "pr_number": pr_number,
                    "title": pr_data.get("title", ""),
                    "description": pr_data.get("body", ""),
                    "base_branch": pr_data.get("base", {}).get("ref", ""),
                    "head_branch": pr_data.get("head", {}).get("ref", ""),
                    "author": pr_data.get("user", {}).get("login", ""),
                    "diff": diff_text,
                    "files": [
                        {
                            "filename": f.get("filename", ""),
                            "status": f.get("status", ""),
                            "additions": f.get("additions", 0),
                            "deletions": f.get("deletions", 0),
                            "patch": f.get("patch", ""),
                        }
                        for f in files_data
                    ],
                    "additions": sum(f.get("additions", 0) for f in files_data),
                    "deletions": sum(f.get("deletions", 0) for f in files_data),
                    "changed_files": len(files_data),
                }
                
        except Exception as e:
            logger.error(f"Error getting PR diff: {e}")
            return None
    
    async def get_commit_diff(
        self, owner: str, repo_name: str, commit_sha: str, token: str
    ) -> Optional[Dict[str, Any]]:
        """Get diff information for a specific commit from GitHub API."""
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.github.com/repos/{owner}/{repo_name}/commits/{commit_sha}"
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Failed to get commit info: {response.status}")
                        return None
                    commit_data = await response.json()

                files_data = commit_data.get("files", [])
                return {
                    "sha": commit_sha,
                    "message": commit_data.get("commit", {}).get("message", ""),
                    "author": commit_data.get("commit", {}).get("author", {}).get("name", ""),
                    "date": commit_data.get("commit", {}).get("author", {}).get("date", ""),
                    "files": [
                        {
                            "filename": f.get("filename", ""),
                            "status": f.get("status", ""),
                            "additions": f.get("additions", 0),
                            "deletions": f.get("deletions", 0),
                            "patch": f.get("patch", ""),
                        }
                        for f in files_data
                    ],
                    "additions": commit_data.get("stats", {}).get("additions", 0),
                    "deletions": commit_data.get("stats", {}).get("deletions", 0),
                    "changed_files": len(files_data),
                }
        except Exception as e:
            logger.error(f"Error getting commit diff: {e}")
            return None

    async def get_latest_commits(
        self, owner: str, repo_name: str, token: str, count: int = 1
    ) -> List[Dict[str, Any]]:
        """Get the latest N commits from a GitHub repo."""
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.github.com/repos/{owner}/{repo_name}/commits?per_page={count}"
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Failed to get commits: {response.status}")
                        return []
                    commits = await response.json()
                    return [
                        {
                            "sha": c.get("sha", ""),
                            "message": c.get("commit", {}).get("message", ""),
                            "author": c.get("commit", {}).get("author", {}).get("name", ""),
                            "date": c.get("commit", {}).get("author", {}).get("date", ""),
                        }
                        for c in commits
                    ]
        except Exception as e:
            logger.error(f"Error getting latest commits: {e}")
            return []

    async def read_file(
        self, user_id: str, file_path: str
    ) -> Optional[str]:
        """Read a file from the user's repository."""
        
        repo_info = self.repos.get(user_id)
        if not repo_info:
            return None
        
        full_path = Path(repo_info.local_path) / file_path
        
        if not full_path.exists():
            return None
        
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return None
    
    async def create_branch(self, user_id: str, branch_name: str, base_branch: str = "main") -> bool:
        """Create a new branch from the base branch in the user's local repo."""
        repo_info = self.repos.get(user_id)
        if not repo_info:
            logger.warning(f"No repository found for user: {user_id}")
            return False

        try:
            import subprocess as _sp
            cwd = str(repo_info.local_path)

            # Fetch latest from remote
            _sp.run(["git", "fetch", "origin"], cwd=cwd, capture_output=True, text=True, timeout=60)

            # Create new branch from origin/base_branch
            proc = _sp.run(
                ["git", "checkout", "-b", branch_name, f"origin/{base_branch}"],
                cwd=cwd, capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                # Branch may already exist, try switching to it
                proc = _sp.run(
                    ["git", "checkout", branch_name],
                    cwd=cwd, capture_output=True, text=True, timeout=30,
                )
                if proc.returncode != 0:
                    logger.error(f"Failed to create/switch to branch {branch_name}: {proc.stderr}")
                    return False

            logger.info(f"✓ Created/switched to branch: {branch_name}")
            return True
        except Exception as e:
            logger.error(f"Error creating branch: {e}")
            return False

    async def apply_fix_to_file(
        self, user_id: str, file_path: str, original_code: str, suggested_code: str
    ) -> bool:
        """Apply a code fix by replacing original_code with suggested_code in the file."""
        repo_info = self.repos.get(user_id)
        if not repo_info:
            return False

        full_path = Path(repo_info.local_path) / file_path
        if not full_path.exists():
            logger.error(f"File not found: {full_path}")
            return False

        # Safety: ensure file is within the repo
        try:
            full_path.resolve().relative_to(Path(repo_info.local_path).resolve())
        except ValueError:
            logger.error(f"Path traversal attempt blocked: {file_path}")
            return False

        try:
            content = full_path.read_text(encoding="utf-8")

            orig = original_code.strip() if original_code else ""
            repl = suggested_code.strip() if suggested_code else ""

            # Strip AI-generated line-number markers like ">>>   18 |" or "  18 |"
            import re as _re_mod
            _line_marker = _re_mod.compile(r'^(?:>>>)?\s*\d+\s*\|\s?', _re_mod.MULTILINE)
            orig = _line_marker.sub('', orig).strip()
            repl = _line_marker.sub('', repl).strip()

            if not orig or not repl:
                logger.warning(f"Empty original_code or suggested_code for {file_path}")
                return False

            if orig in content:
                new_content = content.replace(orig, repl, 1)
            else:
                # Fuzzy match: normalise whitespace before comparing
                import re as _ws_re
                _norm = lambda s: _ws_re.sub(r'\s+', ' ', s.strip())
                if _norm(orig) in _norm(content):
                    # Line-by-line fallback: find matching lines and replace
                    orig_lines = [l.strip() for l in orig.splitlines() if l.strip()]
                    content_lines = content.splitlines(keepends=True)
                    matched_start = None
                    for i in range(len(content_lines)):
                        if orig_lines and orig_lines[0] in content_lines[i]:
                            # Check if subsequent lines match
                            match = True
                            for j, ol in enumerate(orig_lines):
                                if i + j >= len(content_lines) or ol not in content_lines[i + j]:
                                    match = False
                                    break
                            if match:
                                matched_start = i
                                break
                    if matched_start is not None:
                        before = content_lines[:matched_start]
                        after = content_lines[matched_start + len(orig_lines):]
                        # Preserve the indentation of the first matched line
                        indent = content_lines[matched_start][:len(content_lines[matched_start]) - len(content_lines[matched_start].lstrip())]
                        repl_lines = repl.splitlines(keepends=True)
                        indented_repl = []
                        for k, rl in enumerate(repl_lines):
                            indented_repl.append(indent + rl.lstrip() if k > 0 else indent + rl.lstrip())
                        new_content = "".join(before) + "".join(indented_repl) + ("\n" if indented_repl and not indented_repl[-1].endswith("\n") else "") + "".join(after)
                        logger.info(f"Fix applied to {file_path} (fuzzy whitespace match)")
                    else:
                        logger.warning(f"Original code not found in {file_path} — fix skipped")
                        return False
                else:
                    logger.warning(f"Original code not found in {file_path} — fix skipped")
                    return False

            full_path.write_text(new_content, encoding="utf-8")
            logger.info(f"✓ Fix applied to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error applying fix to {file_path}: {e}")
            return False

    async def commit_and_push(
        self, user_id: str, branch_name: str, commit_message: str, token: str = ""
    ) -> Optional[str]:
        """Stage all changes, commit, and push the branch to remote.

        Returns the commit SHA on success, None on failure.
        """
        repo_info = self.repos.get(user_id)
        if not repo_info:
            return None

        try:
            import subprocess as _sp
            cwd = str(repo_info.local_path)

            # Stage only tracked/modified files (avoid picking up untracked utility files)
            proc = _sp.run(["git", "add", "-u"], cwd=cwd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                logger.error(f"git add -u failed: {proc.stderr}")
                # Fallback: try adding only .py/.js/.ts files
                proc = _sp.run(["git", "add", "*.py", "*.js", "*.ts", "*.jsx", "*.tsx"], cwd=cwd, capture_output=True, text=True, timeout=30)
                if proc.returncode != 0:
                    logger.error(f"git add fallback also failed: {proc.stderr}")
                    return None

            # Check if there are changes to commit
            status = _sp.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, timeout=15)
            if not status.stdout.strip():
                logger.warning("No changes to commit")
                return None

            # Commit
            proc = _sp.run(
                ["git", "commit", "-m", commit_message],
                cwd=cwd, capture_output=True, text=True, timeout=30,
                env={**os.environ, "GIT_AUTHOR_NAME": "AutoCure Bot",
                     "GIT_AUTHOR_EMAIL": "autocure@selfhealer.ai",
                     "GIT_COMMITTER_NAME": "AutoCure Bot",
                     "GIT_COMMITTER_EMAIL": "autocure@selfhealer.ai"},
            )
            if proc.returncode != 0:
                logger.error(f"git commit failed: {proc.stderr}")
                return None

            # Get the commit SHA
            sha_proc = _sp.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=15)
            commit_sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else "unknown"

            # Set remote URL with token for push auth
            if token:
                remote_proc = _sp.run(
                    ["git", "remote", "get-url", "origin"],
                    cwd=cwd, capture_output=True, text=True, timeout=15,
                )
                remote_url = remote_proc.stdout.strip()
                auth_url = self._inject_token_in_url(remote_url, token)
                _sp.run(
                    ["git", "remote", "set-url", "origin", auth_url],
                    cwd=cwd, capture_output=True, text=True, timeout=15,
                )

            # Push
            proc = _sp.run(
                ["git", "push", "-u", "origin", branch_name],
                cwd=cwd, capture_output=True, text=True, timeout=120,
            )

            # Restore original remote URL (strip token)
            if token:
                self._strip_token_from_remote(cwd)

            if proc.returncode != 0:
                logger.error(f"git push failed: {proc.stderr}")
                return None

            logger.info(f"✓ Pushed branch {branch_name} (commit {commit_sha[:8]})")
            return commit_sha
        except Exception as e:
            logger.error(f"Error committing and pushing: {e}")
            return None

    async def switch_branch(self, user_id: str, branch_name: str) -> bool:
        """Switch to a specific branch in the user's repo, ensuring a clean state."""
        repo_info = self.repos.get(user_id)
        if not repo_info:
            return False
        try:
            import subprocess as _sp
            cwd = str(repo_info.local_path)
            # Discard any leftover changes before switching
            _sp.run(["git", "reset", "--hard", "HEAD"],
                    cwd=cwd, capture_output=True, text=True, timeout=15)
            _sp.run(["git", "clean", "-fd"],
                    cwd=cwd, capture_output=True, text=True, timeout=15)
            proc = _sp.run(
                ["git", "checkout", branch_name],
                cwd=cwd,
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                logger.error(f"Failed to switch to {branch_name}: {proc.stderr}")
                return False
            logger.info(f"✓ Switched to branch: {branch_name}")
            return True
        except Exception as e:
            logger.error(f"Error switching branch: {e}")
            return False

    async def list_remote_branches(self, user_id: str, token: str = "") -> List[str]:
        """List remote branches for the user's repo via GitHub API."""
        repo_info = self.repos.get(user_id)
        if not repo_info:
            return []

        # Try to get owner/repo from remote URL
        try:
            import subprocess as _sp
            remote_proc = _sp.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(repo_info.local_path),
                capture_output=True, text=True, timeout=15,
            )
            remote_url = remote_proc.stdout.strip()
            host, owner, repo_name = self._parse_repo_url(remote_url)
        except Exception:
            return []

        if not token:
            token = self.default_token or ""
        if not token:
            return []

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.github.com/repos/{owner}/{repo_name}/branches?per_page=100"
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        return []
                    branches = await response.json()
                    return [b["name"] for b in branches]
        except Exception as e:
            logger.error(f"Error listing branches: {e}")
            return []

    async def get_branch_diff(
        self, owner: str, repo_name: str, branch: str, base_branch: str, token: str
    ) -> Optional[Dict[str, Any]]:
        """Get diff between a branch and the base branch via GitHub API."""
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.github.com/repos/{owner}/{repo_name}/compare/{base_branch}...{branch}"
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Failed to get branch diff: {response.status}")
                        return None
                    data = await response.json()

                files_data = data.get("files", [])
                commits = data.get("commits", [])
                return {
                    "branch": branch,
                    "base_branch": base_branch,
                    "ahead_by": data.get("ahead_by", 0),
                    "behind_by": data.get("behind_by", 0),
                    "total_commits": len(commits),
                    "message": commits[-1]["commit"]["message"] if commits else "",
                    "author": commits[-1]["commit"]["author"]["name"] if commits else "",
                    "files": [
                        {
                            "filename": f.get("filename", ""),
                            "status": f.get("status", ""),
                            "additions": f.get("additions", 0),
                            "deletions": f.get("deletions", 0),
                            "patch": f.get("patch", ""),
                        }
                        for f in files_data
                    ],
                    "additions": sum(f.get("additions", 0) for f in files_data),
                    "deletions": sum(f.get("deletions", 0) for f in files_data),
                    "changed_files": len(files_data),
                }
        except Exception as e:
            logger.error(f"Error getting branch diff: {e}")
            return None

    async def post_pr_comment(
        self,
        owner: str,
        repo_name: str,
        pr_number: int,
        token: str,
        body: str,
        dedupe_marker: str = "",
    ) -> Dict[str, Any]:
        """Post a markdown comment on a PR (issue comment endpoint)."""
        if not token:
            return {"ok": False, "url": "", "duplicate": False}
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        payload = {"body": body}
        url = f"https://api.github.com/repos/{owner}/{repo_name}/issues/{pr_number}/comments"
        try:
            async with aiohttp.ClientSession() as session:
                if dedupe_marker:
                    async with session.get(url, headers=headers) as existing_response:
                        if existing_response.status == 200:
                            comments = await existing_response.json()
                            for comment in comments:
                                existing_body = comment.get("body", "")
                                if dedupe_marker in existing_body:
                                    existing_url = comment.get("html_url", "")
                                    logger.info(
                                        f"↷ Skipping duplicate PR comment on #{pr_number}"
                                    )
                                    return {
                                        "ok": True,
                                        "url": existing_url,
                                        "duplicate": True,
                                    }
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status in (200, 201):
                        data = await response.json()
                        comment_url = data.get("html_url", "")
                        logger.info(f"✓ Posted PR comment on #{pr_number}")
                        return {"ok": True, "url": comment_url, "duplicate": False}
                    txt = await response.text()
                    logger.error(f"Failed to post PR comment ({response.status}): {txt[:300]}")
                    return {"ok": False, "url": "", "duplicate": False}
        except Exception as e:
            logger.error(f"Error posting PR comment: {e}")
            return {"ok": False, "url": "", "duplicate": False}

    async def post_commit_comment(
        self,
        owner: str,
        repo_name: str,
        commit_sha: str,
        token: str,
        body: str,
        dedupe_marker: str = "",
    ) -> Dict[str, Any]:
        """Post a markdown comment on a commit."""
        if not token:
            return {"ok": False, "url": "", "duplicate": False}
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        payload = {"body": body}
        url = f"https://api.github.com/repos/{owner}/{repo_name}/commits/{commit_sha}/comments"
        try:
            async with aiohttp.ClientSession() as session:
                if dedupe_marker:
                    async with session.get(url, headers=headers) as existing_response:
                        if existing_response.status == 200:
                            comments = await existing_response.json()
                            for comment in comments:
                                existing_body = comment.get("body", "")
                                if dedupe_marker in existing_body:
                                    existing_url = comment.get("html_url", "")
                                    logger.info(
                                        f"↷ Skipping duplicate commit comment on {commit_sha[:8]}"
                                    )
                                    return {
                                        "ok": True,
                                        "url": existing_url,
                                        "duplicate": True,
                                    }
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status in (200, 201):
                        data = await response.json()
                        comment_url = data.get("html_url", "")
                        logger.info(f"✓ Posted commit comment on {commit_sha[:8]}")
                        return {"ok": True, "url": comment_url, "duplicate": False}
                    txt = await response.text()
                    logger.error(f"Failed to post commit comment ({response.status}): {txt[:300]}")
                    return {"ok": False, "url": "", "duplicate": False}
        except Exception as e:
            logger.error(f"Error posting commit comment: {e}")
            return {"ok": False, "url": "", "duplicate": False}

    async def list_files(
        self, user_id: str, directory: str = "", extensions: Optional[List[str]] = None
    ) -> List[str]:
        """List files in the user's repository."""
        
        repo_info = self.repos.get(user_id)
        if not repo_info:
            return []
        
        base_path = Path(repo_info.local_path) / directory
        
        if not base_path.exists():
            return []
        
        files = []
        
        for root, dirs, filenames in os.walk(base_path):
            # Skip hidden directories and common non-source directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in [
                "node_modules", "__pycache__", "venv", "env", ".git",
                "dist", "build", "target", ".next", ".cache"
            ]]
            
            for filename in filenames:
                if extensions:
                    if not any(filename.endswith(ext) for ext in extensions):
                        continue
                
                rel_path = os.path.relpath(
                    os.path.join(root, filename), 
                    repo_info.local_path
                )
                files.append(rel_path)
        
        return files


# Singleton instance
_github_service: Optional[GitHubService] = None


def get_github_service(repos_base_path: Optional[Path] = None) -> GitHubService:
    """Get or create the GitHub service singleton."""
    global _github_service
    if _github_service is None:
        if repos_base_path is None:
            # Use absolute path relative to project root (parent of src/)
            repos_base_path = Path(__file__).parent.parent.parent / "repos"
        _github_service = GitHubService(repos_base_path)
    return _github_service
