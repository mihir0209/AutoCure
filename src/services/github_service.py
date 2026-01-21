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
            return await self.get_repo_info(user.user_id, local_path)
        
        # Remove existing if force
        if local_path.exists() and force:
            import shutil
            shutil.rmtree(local_path)
        
        # Build clone URL with token
        token = user.access_token or self.default_token
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
            
            process = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "1", "-b", user.base_branch,
                clone_url, str(local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Git clone failed: {stderr.decode()}")
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
    
    async def pull_repository(self, user_id: str) -> bool:
        """
        Pull latest changes for a user's repository.
        
        Returns True if successful, False otherwise.
        """
        repo_info = self.repos.get(user_id)
        if not repo_info:
            logger.warning(f"No repository found for user: {user_id}")
            return False
        
        try:
            process = await asyncio.create_subprocess_exec(
                "git", "pull", "--rebase",
                cwd=str(repo_info.local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Git pull failed: {stderr.decode()}")
                return False
            
            # Update repo info
            repo_info.last_pulled = datetime.utcnow()
            repo_info.latest_commit = await self._get_latest_commit(repo_info.local_path)
            
            logger.info(f"✓ Repository pulled: {repo_info.local_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error pulling repository: {e}")
            return False
    
    async def get_repo_info(self, user_id: str, local_path: Path) -> Optional[RepositoryInfo]:
        """Get information about a cloned repository."""
        
        if not local_path.exists():
            return None
        
        try:
            # Get current branch
            branch_process = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--abbrev-ref", "HEAD",
                cwd=str(local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            branch_stdout, _ = await branch_process.communicate()
            current_branch = branch_stdout.decode().strip()
            
            # Get latest commit
            latest_commit = await self._get_latest_commit(local_path)
            
            return RepositoryInfo(
                user_id=user_id,
                local_path=local_path,
                current_branch=current_branch,
                latest_commit=latest_commit,
                last_pulled=datetime.utcnow(),
            )
            
        except Exception as e:
            logger.error(f"Error getting repo info: {e}")
            return None
    
    async def _get_latest_commit(self, local_path: Path) -> str:
        """Get the latest commit hash."""
        try:
            process = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "HEAD",
                cwd=str(local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            return stdout.decode().strip()
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
        token = user.access_token or self.default_token
        
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
    
    async def read_file(
        self, user_id: str, file_path: str
    ) -> Optional[str]:
        """Read a file from the user's repository."""
        
        repo_info = self.repos.get(user_id)
        if not repo_info:
            return None
        
        full_path = repo_info.local_path / file_path
        
        if not full_path.exists():
            return None
        
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return None
    
    async def list_files(
        self, user_id: str, directory: str = "", extensions: Optional[List[str]] = None
    ) -> List[str]:
        """List files in the user's repository."""
        
        repo_info = self.repos.get(user_id)
        if not repo_info:
            return []
        
        base_path = repo_info.local_path / directory
        
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
            repos_base_path = Path("repos")
        _github_service = GitHubService(repos_base_path)
    return _github_service
