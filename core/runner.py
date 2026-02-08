import asyncio
import json
from typing import Dict, List
from config import CHAIN_NAMES, EVENT_SIGNATURES
from utils import get_logger
from onchain import BlockListenerEVM
from tg_client import TelegramClient, RulesBot
from onchain import EventDetectorEVM
from .rules_manager import RulesManager
from parser import SupplyParser
from .ws_client import WebsocketClient
from utils import get_full_token_list

class Runner:
    def __init__(
        self,
        chains: list = None,
    ):
        self.token_data = None
        self.custom_rules = None
        self.target_events = EVENT_SIGNATURES
        self.chains = chains or [c for c in CHAIN_NAMES if c != 'SOLANA']
        
        self.rules_manager = RulesManager()
        self.token_parser = SupplyParser()
        self.tg_client = TelegramClient(supply_parser=self.token_parser)
        self.detectors: Dict[str, EventDetectorEVM] = {}
        self.listeners: Dict[str, BlockListenerEVM] = {}
        self.ws_client: WebsocketClient = None
        self.rules_bot: RulesBot = None
        self.logger = get_logger("RUNNER")

    async def _init_components(self):
        await self.token_parser.start_scheduled_parsing_loop_task(self.update_token_address_list)
        self.token_data = self.token_parser.main_token_data
        self.ws_client = WebsocketClient(self.tg_client)
        self.custom_rules = self.rules_manager.get_all_rules()
        
        def callback_for_rules_bot():
            self.update_custom_rules()
            self.update_token_address_list()
        self.rules_bot = RulesBot(
            rules_manager=self.rules_manager,
            update_callback=callback_for_rules_bot,
        )
        
        for chain_name in self.chains:
            chain_token_data = self.token_data.get(chain_name, {})
            if not chain_token_data:
                self.logger.warning(f"No token data for {chain_name}, skipping")
                continue
            
            detector = EventDetectorEVM(
                tg_client=self.tg_client,
                chain_name=chain_name,
                token_data=self.token_data,
                custom_rules=self.custom_rules,
                supply_parser=self.token_parser
            )
            self.detectors[chain_name] = detector
            self.ws_client.add_detector(chain_name, detector)
            
            token_address_list = get_full_token_list(chain_name) 
            listener = await BlockListenerEVM.create(
                tg_client=self.tg_client,
                chain_name=chain_name,
                token_address_list=token_address_list,
                target_events=self.target_events,
            )
            self.listeners[chain_name] = listener
            self.ws_client.add_listener(chain_name, listener)
            
            self.logger.success(f"Initialized {chain_name}")

    def update_custom_rules(self,):
        self.custom_rules = self.rules_manager.get_all_rules()
        for chain_name, detector in self.detectors.items():
            detector.update_custom_rules(self.custom_rules)
        self.logger.info(f"Updated custom rules for {len(self.detectors)} detectors")
    
    def reload_filters(self):
        for chain_name, detector in self.detectors.items():
            detector.reload_filters()
        self.logger.info(f"Reloaded filters for {len(self.detectors)} detectors")

    def update_token_address_list(self):
        for chain_name, listener in self.listeners.items():
            token_list = get_full_token_list(chain_name)
            if not token_list:
                self.logger.warning(f"No token list for {chain_name}, skipping")
                continue
            listener.update_token_address_list(token_list)
            self.logger.info(f"Updated token list for {chain_name}")

    async def start(self):
        await self._init_components()
        
        rules_bot_task = asyncio.create_task(self.rules_bot.start())
        tg_bot_status_task = asyncio.create_task(self.tg_client.start_status_monitor(self.chains))
        
        try:
            await self.ws_client.start()
        finally:
            rules_bot_task.cancel()
            tg_bot_status_task.cancel()
            await self.rules_bot.stop()
            try:
                await rules_bot_task
                await tg_bot_status_task
            except asyncio.CancelledError:
                pass
