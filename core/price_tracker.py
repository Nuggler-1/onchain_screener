"""
Price tracker for monitoring token prices after usd_based_transfer signals.
Schedules delayed price checks and triggers alerts on significant drops.
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Callable, Awaitable
from utils import get_logger, Gecko


@dataclass
class PendingPriceCheck:
    """Represents a scheduled price check"""
    message_id: int
    chat_id: str
    chain: str
    contract: str
    ticker: str
    initial_price: float
    check_time: datetime
    threshold_percent: float
    cmc_id: Optional[int] = None


class PriceTracker:
    """Tracks token prices after usd_based_transfer signals and alerts on drops"""
    
    def __init__(self, reply_callback: Callable[[PendingPriceCheck, float, float], Awaitable[None]]):
        """
        Args:
            reply_callback: Async function to call when price drop detected.
                           Receives (pending_check, new_price, drop_percent)
        """
        self.pending_checks: Dict[str, PendingPriceCheck] = {}  # key: f"{chain}:{contract}:{message_id}"
        self.gecko = Gecko()
        self.logger = get_logger("PRICE_TRACKER")
        self.reply_callback = reply_callback
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    def schedule_check(
        self,
        message_id: int,
        chat_id: str,
        chain: str,
        contract: str,
        ticker: str,
        initial_price: float,
        delay_minutes: int,
        threshold_percent: float,
        cmc_id: Optional[int] = None
    ):
        """Schedule a price check after delay_minutes"""
        check_time = datetime.now(timezone.utc).timestamp() + (delay_minutes * 60)
        check_time_dt = datetime.fromtimestamp(check_time, tz=timezone.utc)
        
        key = f"{chain}:{contract}:{message_id}"
        self.pending_checks[key] = PendingPriceCheck(
            message_id=message_id,
            chat_id=chat_id,
            chain=chain,
            contract=contract,
            ticker=ticker,
            initial_price=initial_price,
            check_time=check_time_dt,
            threshold_percent=threshold_percent,
            cmc_id=cmc_id
        )
        
        self.logger.info(
            f"Scheduled price check for {ticker} ({chain}) in {delay_minutes}m. "
            f"Initial price: ${initial_price:.6f}, threshold: {threshold_percent}%"
        )
    
    async def _check_price(self, pending: PendingPriceCheck) -> Optional[float]:
        """Get current price for a pending check"""
        try:
            price = await self.gecko.get_token_price_simple(pending.chain, pending.contract)
            return price
        except Exception as e:
            self.logger.error(f"Error fetching price for {pending.ticker}: {e}")
            return None
    
    async def _process_pending_checks(self):
        """Process all pending checks that have reached their check time"""
        now = datetime.now(timezone.utc)
        keys_to_remove = []
        
        for key, pending in list(self.pending_checks.items()):
            if now >= pending.check_time:
                self.logger.debug(f"Processing price check for {pending.ticker}")
                
                new_price = await self._check_price(pending)
                if new_price is not None and pending.initial_price > 0:
                    price_change_percent = ((new_price - pending.initial_price) / pending.initial_price) * 100
                    
                    # Check if price dropped more than threshold
                    if price_change_percent <= -pending.threshold_percent:
                        self.logger.info(
                            f"Price drop detected for {pending.ticker}: "
                            f"${pending.initial_price:.6f} -> ${new_price:.6f} ({price_change_percent:.2f}%)"
                        )
                        try:
                            await self.reply_callback(pending, new_price, price_change_percent)
                        except Exception as e:
                            self.logger.error(f"Error in reply callback: {e}")
                    else:
                        self.logger.debug(
                            f"No significant drop for {pending.ticker}: {price_change_percent:.2f}%"
                        )
                
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.pending_checks[key]
    
    async def _monitor_loop(self):
        """Background loop that checks pending price checks every 30 seconds"""
        self.logger.info("Price tracker monitor started")
        while self._running:
            try:
                await self._process_pending_checks()
            except Exception as e:
                self.logger.error(f"Error in price tracker loop: {e}")
            await asyncio.sleep(30)
    
    def start(self):
        """Start the background monitoring task"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        self.logger.info("Price tracker started")
    
    def stop(self):
        """Stop the background monitoring task"""
        self._running = False
        if self._task:
            self._task.cancel()
        self.logger.info("Price tracker stopped")
    
    @property
    def pending_count(self) -> int:
        """Number of pending price checks"""
        return len(self.pending_checks)
