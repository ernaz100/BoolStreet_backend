"""Trading scheduler for automatic execution of LLM traders.

This module manages the scheduling of trading agents based on their
configured trading_frequency. It uses APScheduler to run traders
at specified intervals.
"""

import json
import logging
from typing import Dict, Optional, List
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from db.database import get_session
from db.db_models import UserModel

logger = logging.getLogger(__name__)

# Supported trading frequencies and their interval configurations
FREQUENCY_CONFIG = {
    "1min": {"minutes": 1},
    "5min": {"minutes": 5},
    "15min": {"minutes": 15},
    "1hour": {"hours": 1},
    "4hour": {"hours": 4},
    "1day": {"days": 1},
}


class TradingScheduler:
    """Manages scheduled execution of trading agents."""
    
    def __init__(self):
        """Initialize the trading scheduler."""
        self.scheduler = BackgroundScheduler(daemon=True)
        self._is_running = False
        
    def start(self):
        """Start the scheduler and sync active traders."""
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            logger.info("Trading scheduler started")
            # Sync all active traders on startup
            self.sync_active_traders()
    
    def stop(self):
        """Stop the scheduler."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("Trading scheduler stopped")
    
    def parse_frequency(self, frequency: str) -> Optional[Dict]:
        """Parse trading frequency string to interval configuration.
        
        Args:
            frequency: Frequency string (e.g., '1hour', '5min', '1day')
            
        Returns:
            Dictionary with interval configuration or None if invalid
        """
        frequency = frequency.lower().strip()
        return FREQUENCY_CONFIG.get(frequency)
    
    def get_job_id(self, trader_id: int) -> str:
        """Generate a unique job ID for a trader.
        
        Args:
            trader_id: The trader's database ID
            
        Returns:
            Unique job ID string
        """
        return f"trader_{trader_id}"
    
    def add_trader(self, trader_id: int, trading_frequency: str) -> bool:
        """Add a trader to the scheduler.
        
        Args:
            trader_id: The trader's database ID
            trading_frequency: The trading frequency string
            
        Returns:
            True if successfully added, False otherwise
        """
        job_id = self.get_job_id(trader_id)
        
        # Remove existing job if present
        self.remove_trader(trader_id)
        
        # Parse frequency
        interval_config = self.parse_frequency(trading_frequency)
        if not interval_config:
            logger.error(f"Invalid trading frequency '{trading_frequency}' for trader {trader_id}")
            return False
        
        try:
            # Create the job
            self.scheduler.add_job(
                func=self._execute_trader_job,
                trigger=IntervalTrigger(**interval_config),
                id=job_id,
                name=f"Trader {trader_id} ({trading_frequency})",
                args=[trader_id],
                replace_existing=True,
                max_instances=1,  # Prevent overlapping executions
                coalesce=True,    # Combine missed runs into one
            )
            logger.info(f"Added trader {trader_id} to scheduler with frequency {trading_frequency}")
            return True
        except Exception as e:
            logger.error(f"Failed to add trader {trader_id} to scheduler: {e}")
            return False
    
    def remove_trader(self, trader_id: int) -> bool:
        """Remove a trader from the scheduler.
        
        Args:
            trader_id: The trader's database ID
            
        Returns:
            True if successfully removed (or didn't exist), False on error
        """
        job_id = self.get_job_id(trader_id)
        
        try:
            job = self.scheduler.get_job(job_id)
            if job:
                self.scheduler.remove_job(job_id)
                logger.info(f"Removed trader {trader_id} from scheduler")
            return True
        except Exception as e:
            logger.error(f"Failed to remove trader {trader_id} from scheduler: {e}")
            return False
    
    def sync_active_traders(self):
        """Sync all active traders from database to scheduler.
        
        This removes jobs for inactive traders and adds jobs for
        active traders that aren't already scheduled.
        """
        try:
            with get_session() as session:
                # Get all active traders
                active_traders = session.query(UserModel).filter(
                    UserModel.active == True
                ).all()
                
                # Get current scheduled job IDs
                scheduled_job_ids = {job.id for job in self.scheduler.get_jobs()}
                active_trader_job_ids = set()
                
                for trader in active_traders:
                    job_id = self.get_job_id(trader.id)
                    active_trader_job_ids.add(job_id)
                    
                    # Get trading frequency from weights
                    trading_frequency = "1hour"  # Default
                    if trader.weights:
                        try:
                            config = json.loads(trader.weights)
                            trading_frequency = config.get("trading_frequency", "1hour")
                        except json.JSONDecodeError:
                            pass
                    
                    # Add to scheduler if not already scheduled
                    if job_id not in scheduled_job_ids:
                        self.add_trader(trader.id, trading_frequency)
                
                # Remove jobs for traders that are no longer active
                # Only remove trader jobs (those starting with 'trader_')
                for job_id in scheduled_job_ids:
                    if job_id.startswith('trader_') and job_id not in active_trader_job_ids:
                        try:
                            self.scheduler.remove_job(job_id)
                            logger.info(f"Removed inactive trader job: {job_id}")
                        except Exception as e:
                            logger.warning(f"Failed to remove job {job_id}: {e}")
                
                logger.info(f"Synced {len(active_traders)} active traders to scheduler")
                
        except Exception as e:
            logger.error(f"Error syncing active traders: {e}")
    
    def _execute_trader_job(self, trader_id: int):
        """Execute a trader - this is called by the scheduler.
        
        Args:
            trader_id: The trader's database ID
        """
        # Import here to avoid circular imports
        from layers.execution import execute_trader
        
        logger.info(f"[Scheduler] Executing trader {trader_id}")
        
        try:
            with get_session() as session:
                trader = session.query(UserModel).filter(
                    UserModel.id == trader_id,
                    UserModel.active == True
                ).first()
                
                if not trader:
                    logger.warning(f"Trader {trader_id} not found or inactive, removing from scheduler")
                    self.remove_trader(trader_id)
                    return
                
                # Execute the trader
                result = execute_trader(trader)
                
                if result.get("success"):
                    decision = result.get("decision")
                    trade_result = result.get("trade_result", {})
                    logger.info(
                        f"[Scheduler] Trader {trader_id} executed: "
                        f"decision={decision.decision if decision else 'N/A'}, "
                        f"coin={decision.coin if decision else 'N/A'}, "
                        f"trade_success={trade_result.get('success', False)}"
                    )
                else:
                    logger.error(f"[Scheduler] Trader {trader_id} execution failed: {result.get('error')}")
                    
        except Exception as e:
            logger.error(f"[Scheduler] Error executing trader {trader_id}: {e}")
    
    def get_scheduled_traders(self) -> List[Dict]:
        """Get list of all scheduled traders.
        
        Returns:
            List of dictionaries with trader job info
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            if job.id.startswith('trader_'):
                trader_id = int(job.id.replace('trader_', ''))
                jobs.append({
                    "trader_id": trader_id,
                    "job_id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                })
        return jobs
    
    def trigger_trader_now(self, trader_id: int) -> Dict:
        """Manually trigger a trader execution immediately.
        
        Args:
            trader_id: The trader's database ID
            
        Returns:
            Execution result dictionary
        """
        from layers.execution import execute_trader
        
        logger.info(f"[Manual] Triggering trader {trader_id}")
        
        try:
            with get_session() as session:
                trader = session.query(UserModel).filter(
                    UserModel.id == trader_id
                ).first()
                
                if not trader:
                    return {"success": False, "error": "Trader not found"}
                
                # Execute the trader
                result = execute_trader(trader)
                return result
                
        except Exception as e:
            logger.error(f"[Manual] Error executing trader {trader_id}: {e}")
            return {"success": False, "error": str(e)}


# Global scheduler instance
trading_scheduler = TradingScheduler()

