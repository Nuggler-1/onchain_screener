"""
Telegram notification client using aiogram
Sends messages to Telegram if API credentials are configured, otherwise skips silently
"""
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from parser import SupplyParser
from utils import get_logger
from typing import Optional
from config import ALERT_TG_BOT_TOKEN, TECH_ALERTS_CHAT_ID, USER_ALERTS_CHAT_ID
from .consts import ARKHAM_URL, DEXSCREENER_BASE_URL, SCAN_URL, OKX_DEX_URL, futures_link_map
import asyncio
from datetime import datetime
import re
from utils import Gecko


def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram Markdown"""
    # Characters that need to be escaped in Markdown
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', str(text))


class TelegramClient:

    def __init__(
        self, 
        bot_token: Optional[str] = ALERT_TG_BOT_TOKEN, 
        tech_alerts: Optional[str] = TECH_ALERTS_CHAT_ID,
        user_alerts: Optional[str] = USER_ALERTS_CHAT_ID,
        supply_parser: Optional[SupplyParser] = None
    ):
        self.logger = get_logger("TG_CLIENT")
        self.bot_token = bot_token
        self.tech_alerts = tech_alerts
        self.user_alerts = user_alerts
        self.enabled = bool(bot_token and tech_alerts and user_alerts)
        self._status_message_id = None
        self._status_monitor_task = None
        self.gecko = Gecko()
        self.supply_parser = supply_parser

        if self.enabled:
            self.bot = Bot(token=self.bot_token)
            self.logger.info("Telegram notifications enabled")
        else:
            self.bot = None
            self.logger.info("Telegram notifications disabled (no API key configured)")
    
    async def close(self):
        if self._status_monitor_task:
            self._status_monitor_task.cancel()
            try:
                await self._status_monitor_task
            except asyncio.CancelledError:
                pass
        
        if self.enabled and self.bot:
            await self.bot.session.close()
            self.logger.debug("Bot session closed")

    async def send_alert(
        self,
        signal:dict 
    ):
        """
        {   
            "chain": chain,
            "direction": trade_direction,
            "ticker": ticker,
            "contract": token_address,
            "event_type": event_type,
            "supply_percent": supply_percent_in_action,
            "auto_open": auto_open, 
            "message_tier": message_tier,
            "from_addresses": [list of addresses],
            "to_addresses": [list of addresses],
            "filter_matches": {"from": [names], "to": [names]}
        }
        """
        def format_mcap(value: float) -> str:
            if not value:
                return "0"
            if value >= 1_000_000_000:
                return f"{value / 1_000_000_000:.1f}b"
            return f"{value / 1_000_000:.1f}m"

        def format_volume(value: float) -> str:
            if not value:
                return "0"
            if value >= 1_000_000_000:
                return f"{value / 1_000_000_000:.1f}b"
            if value >= 1_000_000:
                return f"{value / 1_000_000:.1f}m"
            return f"{value / 1_000:.1f}k"

        if not self.enabled:
            return False

        #token_data = await self.gecko.get_token_data_for_message(signal['chain'].upper(), signal['contract'])
        # price = token_data.get('price', 0)
        # mcap = token_data.get('mcap', 0)
        # volume = token_data.get('volume', 0)
        ticker = signal.get('ticker', '')
        chain = signal.get('chain', '')
        contract = signal.get('contract', '')

        supported_futures = self.supply_parser.main_token_data.get(chain.upper(), {}).get(contract, {}).get('supported_futures', []) 
        token_data = await self.supply_parser._get_cmc_quote_for_token_ticker(ticker)
        
        mcap = token_data.get('market_cap',0)
        if not mcap: 
            mcap = token_data.get("fully_diluted_market_cap", 0)
        price = token_data.get('price', 0)
        volume = token_data.get('volume_24h', 0)

        direction = signal.get('direction', '')
        event_type = signal.get('event_type', '')
        supply_percent = signal.get('supply_percent', 0) * 100
        tx_url = f"{ARKHAM_URL}tx/{signal.get('tx_hash', '')}"
        dexscreener_url = f"{DEXSCREENER_BASE_URL}/{chain}/{signal.get('contract', '')}"

        arrow = "BUY ↗️" if direction.lower() == "long" else "SELL ↘️"
        message_tier = signal.get('message_tier', '')
        
        message = ""
        message += f"*{escape_markdown(message_tier)}* | `{escape_markdown(ticker).upper()}` | {escape_markdown(chain.upper())}\n\n"
        match event_type: 
            case "hidden_binance_alpha":
                usd_value = signal.get('usd_amount', 0)
                token_amount = signal.get('token_amount', 0)
                alpha_wallet = signal.get('wallet_address', '')
                alpha_index_wallet = signal.get('wallet_index', 0)
                message += f"*Tokens:* {token_amount:,.2f}\n" 
                message += f"*USD total:* ${usd_value:,.2f}\n"
                message += f"*Binance wallet:* [address #{alpha_index_wallet}](https://bscscan.com/address/{alpha_wallet})\n\n"
            case "usd_based_transfer":
                usd_value = signal.get('usd_amount', 0)
                token_amount = signal.get('token_amount', 0)
                message += f"*Tokens:* {token_amount:,.2f}\n" 
                message += f"*USD total:* ${usd_value:,.2f}\n\n"
            case _:
                message += f"*Event:* {supply_percent:.2f}% circ. supply *{escape_markdown(event_type).lower()}ed*\n" 
                message += f"*Trade:* {arrow}\n\n"
        
        def format_address_with_name(address: str, names_map: dict) -> str:
            short_addr = f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address
            address_url = f"{ARKHAM_URL}address/{address}"
            name = names_map.get(address) or names_map.get(address.lower())
            if name:
                return f"*{escape_markdown(name)}* ([{short_addr}]({address_url}))"
            return f"[{short_addr}]({address_url})"
        
        from_addresses = signal.get('from_addresses', [])
        to_addresses = signal.get('to_addresses', [])
        filter_matches = signal.get('filter_matches', {})
        from_names = filter_matches.get('from', {}) if filter_matches else {}
        to_names = filter_matches.get('to', {}) if filter_matches else {}
        
        if from_addresses or to_addresses:
            message += "*Addresses:*\n"
            if from_addresses:
                formatted_from = [format_address_with_name(addr, from_names) for addr in from_addresses[:3]]
                message += f"  • From: {', '.join(formatted_from)}"
                if len(from_addresses) > 3:
                    message += f" (+{len(from_addresses)-3} more)"
                message += "\n"
            if to_addresses:
                formatted_to = [format_address_with_name(addr, to_names) for addr in to_addresses[:3]]
                message += f"  • To: {', '.join(formatted_to)}"
                if len(to_addresses) > 3:
                    message += f" (+{len(to_addresses)-3} more)"
                message += "\n"
            message += "\n"
        
        message += f"*Price:* ${price:.5f}\n"
        message += f"*MCap:* ${format_mcap(mcap)}\n"
        message += f"*Volume 24h:* ${format_volume(volume)}\n\n"
        message += f"*Chain name:* {chain.upper()}\n"
        message += f"*Ticker:* `{ticker.upper()}`\n"
        message += f"*Contract:* `{signal.get('contract', '')}`\n"
        message += f"*Transaction:* [open link]({tx_url})\n\n"

        # Build keyboard dynamically based on supported futures
        keyboard_rows = []
        
        # First row: DexScreener and DEX
        dex_url =f"{OKX_DEX_URL}{chain}/{contract}"
        first_row = [
            InlineKeyboardButton(text="📊 DexScreener", url=dexscreener_url),
            InlineKeyboardButton(text="🦄 DEX", url=dex_url)
        ]
        keyboard_rows.append(first_row)
        
        # Build futures buttons from supported_futures list
        if supported_futures:
            futures_buttons = []
            for exchange_slug in supported_futures:
                url, emoji = futures_link_map(exchange_slug, ticker)
                if url and emoji:
                    button_text = f"{emoji} {exchange_slug.upper()}"
                    futures_buttons.append(InlineKeyboardButton(text=button_text, url=url))
            
            # Split futures buttons into rows of 2
            for i in range(0, len(futures_buttons), 2):
                row = futures_buttons[i:i+2]
                keyboard_rows.append(row)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        try:
            await self.bot.send_message(
                chat_id=self.user_alerts,
                text=message,
                parse_mode="Markdown",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            self.logger.info(f"Alert sent for {ticker}")
            return True
        except Exception as e:
            self.logger.error(f"Error sending alert: {e}")
            return False
    
    
    async def send_message(
        self, 
        message: str, 
        parse_mode: str = "Markdown",
        disable_notification: bool = False
    ) -> bool:
        """
        Send a text message to Telegram
        
        Args:
            message: Message text to send
            parse_mode: Parse mode (HTML, Markdown, or None)
            disable_notification: Send silently without notification
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            
            await self.bot.send_message(
                chat_id=self.tech_alerts,
                text=message,
                parse_mode=parse_mode,
                disable_notification=disable_notification
            )
            self.logger.debug("Message sent successfully")
            return True
                        
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            return False
    
    
    async def send_error_alert(
        self,
        error_type: str,
        error_message: str,
        context: Optional[str] = None
    ) -> bool:
        """
        Send an error alert
        
        Args:
            error_type: Type of error (e.g., "SWAP_FAILED", "RPC_ERROR")
            error_message: Error message
            context: Additional context (optional)
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False
        
        # Escape special characters in error messages
        safe_error_type = escape_markdown(error_type)
        safe_error_message = escape_markdown(error_message)
        
        message = f"⚠️ *Error Alert*\n\n"
        message += f"*Type:* {safe_error_type}\n\n"
        message += f"*Message:* {safe_error_message}\n\n"
        
        if context:
            safe_context = escape_markdown(context)
            message += f"*Context:* {safe_context}\n\n"
        
        return await self.send_message(message)
    
    async def start_status_monitor(self, chains: list[str]) -> bool:
        """
        Args:
            chains: List of enabled chains
            
        Returns:
            True if started successfully, False otherwise
        """
        if not self.enabled:
            self.logger.warning("Telegram notifications disabled (no API key configured)")
            return False
        
        try:
            # Send initial message
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = "*Monitoring Bot Started*\n\n"
            message += f"*Active Chains:*\n\n"
            for chain in chains:
                message += f"  • {chain}\n"
            message += f"\n_Monitoring for events_\n"
            message += f"\n*Last Update:* `{current_time}`"
            
            sent_message = await self.bot.send_message(
                chat_id=self.tech_alerts,
                text=message,
                parse_mode="Markdown"
            )
            self._status_message_id = sent_message.message_id
            self.logger.info("Status monitor message sent")
            
            # Start background task to update message every 20 seconds
            self._status_monitor_task = asyncio.create_task(
                self._update_status_loop(chains)
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting status monitor: {e}")
            return False
    
    async def _update_status_loop(self, chains: list[str]):
        """
        Background task that updates the status message every 20 seconds
        
        Args:
            chains: List of enabled chains
        """

        while True:
            await asyncio.sleep(20)
            
            if not self._status_message_id:
                break
            
            try:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                message = "*Monitoring Bot Started*\n\n"
                message += f"*Active Chains:*\n\n"
                for chain in chains:
                    message += f"  • {chain}\n"
                message += f"\n_Monitoring for events_\n"
                message += f"\n*Last Update:* `{current_time}`"
                
                await self.bot.edit_message_text(
                    chat_id=self.tech_alerts,
                    message_id=self._status_message_id,
                    text=message,
                    parse_mode="Markdown"
                )
                #self.logger.debug("Status message updated")
                
            except Exception as e:
                self.logger.error(f"Error updating status message: {e}")
                