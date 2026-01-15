"""
Main Orchestrator for the Self-Healing Software System.
Manages all subprocesses and coordinates the healing workflow.
"""

import asyncio
import subprocess
import sys
import signal
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from utils.logger import setup_colored_logger
from subprocesses.log_watcher import LogWatcher
from subprocesses.error_processor import ErrorProcessor
from subprocesses.git_handler import GitHandler
from subprocesses.email_notifier import EmailNotifier
from agents.healing_agent import HealingAgent
from utils.models import HealingReport, ErrorInfo


logger = setup_colored_logger("orchestrator")


class SelfHealingOrchestrator:
    """
    Main orchestrator that manages the self-healing workflow.
    
    Workflow:
    1. Start target service (Node.js demo server)
    2. Monitor logs for errors/warnings (subprocess1)
    3. When error detected, process logs to trace origin (subprocess3)
    4. AI agent generates fix proposals and tests
    5. Test loop until fix passes or max attempts reached
    6. Git branch creation with tested code (subprocess4)
    7. Email notification with results
    """
    
    def __init__(self):
        self.config = load_config()
        self.log_watcher: Optional[LogWatcher] = None
        self.error_processor: Optional[ErrorProcessor] = None
        self.healing_agent: Optional[HealingAgent] = None
        self.git_handler: Optional[GitHandler] = None
        self.email_notifier: Optional[EmailNotifier] = None
        self.target_process: Optional[subprocess.Popen] = None
        self.running = False
        self.healing_reports: list[HealingReport] = []
        
    async def initialize(self):
        """Initialize all components"""
        logger.info("═" * 60)
        logger.info("   SELF-HEALING SOFTWARE SYSTEM - INITIALIZING")
        logger.info("═" * 60)
        
        # Initialize components
        self.log_watcher = LogWatcher(
            log_file=self.config.log_file,
            watch_interval=self.config.log_watch_interval,
        )
        
        self.error_processor = ErrorProcessor(
            target_service_path=self.config.target_service_path,
        )
        
        self.healing_agent = HealingAgent(
            ai_config=self.config.ai,
            max_attempts=self.config.max_fix_attempts,
            test_timeout=self.config.test_timeout,
        )
        
        self.git_handler = GitHandler(
            repo_path=self.config.git.repo_path,
            branch_prefix=self.config.git.branch_prefix,
        )
        
        self.email_notifier = EmailNotifier(
            smtp_server=self.config.email.smtp_server,
            smtp_port=self.config.email.smtp_port,
            sender_email=self.config.email.sender_email,
            sender_password=self.config.email.sender_password,
            admin_email=self.config.email.admin_email,
            enabled=self.config.email.enable_notifications,
        )
        
        logger.info("✓ All components initialized")
        logger.info(f"  AI Provider: {self.config.ai.provider}")
        logger.info(f"  Target Service: {self.config.target_service_path}")
        logger.info(f"  Log File: {self.config.log_file}")
        
    async def start_target_service(self):
        """Start the target Node.js service (subprocess2)"""
        logger.info("Starting target service (Node.js demo server)...")
        
        service_path = self.config.target_service_path
        server_file = service_path / "server.js"
        
        if not server_file.exists():
            logger.error(f"Server file not found: {server_file}")
            return False
        
        # Ensure log directory exists
        self.config.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Open log file for service output
        log_file_handle = open(self.config.log_file, "a", encoding="utf-8")
        
        try:
            self.target_process = subprocess.Popen(
                ["node", str(server_file)],
                cwd=str(service_path),
                stdout=log_file_handle,
                stderr=subprocess.STDOUT,
                shell=False,
            )
            logger.info(f"✓ Target service started (PID: {self.target_process.pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to start target service: {e}")
            return False
    
    async def stop_target_service(self):
        """Stop the target service"""
        if self.target_process:
            logger.info("Stopping target service...")
            self.target_process.terminate()
            try:
                self.target_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.target_process.kill()
            self.target_process = None
            logger.info("✓ Target service stopped")
    
    async def on_error_detected(self, error_info: ErrorInfo):
        """
        Handle detected error - main healing workflow.
        
        subprocess3 -> process(logs) -> AI thread -> fix proposal -> test loop
        """
        logger.info("═" * 60)
        logger.info("   ERROR DETECTED - INITIATING HEALING PROCESS")
        logger.info("═" * 60)
        logger.info(f"Error Type: {error_info.error_type}")
        logger.info(f"Message: {error_info.message}")
        logger.info(f"Source: {error_info.source_file}:{error_info.line_number}")
        
        # Process error to trace origin (subprocess3)
        traced_error = await self.error_processor.trace_error_origin(error_info)
        logger.info(f"✓ Error traced to source: {traced_error.source_file}")
        
        # AI agent generates fix and runs test loop
        report = await self.healing_agent.heal(traced_error)
        
        if report.status == "success" and report.final_fix:
            # Create git branch with fix (subprocess4)
            branch_name, commit_hash = await self.git_handler.create_fix_branch(
                fix=report.final_fix,
                error_info=traced_error,
            )
            report.git_branch = branch_name
            report.git_commit = commit_hash
            logger.info(f"✓ Git branch created: {branch_name}")
            
        # Send email notification
        await self.email_notifier.send_healing_report(report)
        logger.info("✓ Notification email sent")
        
        self.healing_reports.append(report)
        
        # Print report summary
        print(report.summary())
        
        return report
    
    async def run(self):
        """Main run loop"""
        self.running = True
        
        await self.initialize()
        
        # Start target service
        if not await self.start_target_service():
            logger.error("Failed to start target service. Exiting.")
            return
        
        # Give service time to start
        await asyncio.sleep(2)
        
        logger.info("═" * 60)
        logger.info("   MONITORING FOR ERRORS...")
        logger.info("═" * 60)
        
        # Start log watcher with error callback
        try:
            async for error_info in self.log_watcher.watch():
                if not self.running:
                    break
                    
                if error_info:
                    await self.on_error_detected(error_info)
                    
        except asyncio.CancelledError:
            logger.info("Monitoring cancelled")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Clean shutdown of all components"""
        logger.info("Initiating shutdown...")
        self.running = False
        
        await self.stop_target_service()
        
        if self.log_watcher:
            self.log_watcher.stop()
        
        logger.info("═" * 60)
        logger.info("   SELF-HEALING SYSTEM SHUTDOWN COMPLETE")
        logger.info("═" * 60)


async def main():
    """Entry point"""
    orchestrator = SelfHealingOrchestrator()
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal...")
        orchestrator.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await orchestrator.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        await orchestrator.shutdown()


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   ███████╗███████╗██╗     ███████╗    ██╗  ██╗███████╗ █████╗ ║
    ║   ██╔════╝██╔════╝██║     ██╔════╝    ██║  ██║██╔════╝██╔══██╗║
    ║   ███████╗█████╗  ██║     █████╗█████╗███████║█████╗  ███████║║
    ║   ╚════██║██╔══╝  ██║     ██╔══╝╚════╝██╔══██║██╔══╝  ██╔══██║║
    ║   ███████║███████╗███████╗██║         ██║  ██║███████╗██║  ██║║
    ║   ╚══════╝╚══════╝╚══════╝╚═╝         ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝║
    ║                                                               ║
    ║           AI-Driven Self-Healing Software System              ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    asyncio.run(main())
