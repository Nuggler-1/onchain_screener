from tg_client import TelegramClient

from typing import Dict
from config import CHAIN_NAMES, RPC
from typing import Literal
from .log_parser import EventParser
from .event_filter import EventFilter
from config import FILTER_CONFIG, EVENT_TRADE_DIRECTION, BINANCE_ALPHA_WALLETS, MIN_PARSED_PRICE_SIZE_TO_CHECK
from utils import Gecko, get_logger
from web3 import Web3

class EventDetectorEVM:
    def __init__(
        self, 
        tg_client:TelegramClient,
        chain_name:Literal[*CHAIN_NAMES],
        token_data: dict,
        custom_rules: dict
    ):
        self.tg_client = tg_client
        self.chain_name = chain_name
        self.token_data = token_data[self.chain_name]
        self.custom_rules = custom_rules
        self.gecko = Gecko()
        self.logger = get_logger(chain_name)
        self.event_filter = EventFilter()
        self.w3 = Web3(Web3.HTTPProvider(RPC[chain_name]))

    
    def _get_event_trade_direction(self, event_type:str) -> Literal['long', 'short']: 
        return EVENT_TRADE_DIRECTION.get(event_type, '')

    def _get_event_config(self, event_type:str, supply_percent_in_action:float, usd_size:float = 0) -> dict:
        for config in FILTER_CONFIG[event_type]:
            if not config['enabled']:
                continue 
            if event_type in ("usd_based_transfer", "hidden_binance_alpha"):
                if config['min_usd_size'] <= usd_size < config['max_usd_size']:
                    return config
            elif config['min_supply_percent'] <= supply_percent_in_action < config['max_supply_percent']:
                return config
        return {}

    def update_custom_rules(self, custom_rules: dict):
        self.custom_rules = custom_rules
    
    def reload_filters(self):
        self.event_filter.reload_filters()
        self.logger.info(f"Reloaded event filters for {self.chain_name}")

    async def _detect_alpha(self, token_address:str, event_data:dict):
        for transfer in event_data['transfers']:
            if transfer['to'].lower() in BINANCE_ALPHA_WALLETS:
                wallet_address = transfer['to']
                wallet_index = BINANCE_ALPHA_WALLETS.index(transfer['to'].lower()) + 1
                event_type = "hidden_binance_alpha"
                token_decimals = self.token_data[token_address]['decimals']
                token_amount_in_transfer = transfer['amount']/10**token_decimals

                usd_size = await self._check_usd_size_transfer(token_address, event_type, event_data, MIN_PARSED_PRICE_SIZE_TO_CHECK, wallet_address)
                event_config = self._get_event_config(event_type, token_amount_in_transfer, usd_size)
                
                if not event_config:
                    self.logger.warning(f"No config found for binance alpha event: usd_size={usd_size}, supply_percent_in_action={token_amount_in_transfer}, wallet_address={wallet_address}")
                    return {}
                
                return {
                    "direction": EVENT_TRADE_DIRECTION[event_type],
                    "ticker": self.token_data[token_address]['ticker'],
                    "contract": token_address,
                    "event_type": event_type,
                    "wallet_address": wallet_address,
                    "wallet_index": wallet_index,
                    "token_amount": token_amount_in_transfer,
                    "usd_amount": usd_size,
                    "auto_open": event_config.get('auto_open'), 
                    "message_tier": event_config.get('message_tier')
                }
        return {}

    async def _check_usd_size_transfer(self, token_address: str, event_type:str, event_data:dict, min_cached_size:float, wallet_to:str):
        last_price = self.token_data.get(token_address, {}).get('last_price', 0)
        token_amount_in_event = event_data['total']/10**self.token_data[token_address]['decimals']
        if last_price == 0: 
            price = await self.gecko.get_token_price_simple(self.chain_name, token_address)
            usd_size = price * token_amount_in_event
            return usd_size
        else: 
            usd_size_cached = last_price*token_amount_in_event
            if usd_size_cached > min_cached_size:
                price = await self.gecko.get_token_price_simple(self.chain_name, token_address)
                usd_size = price * token_amount_in_event
                return usd_size
            else: 
                #self.logger.warning(f"{event_type}: token {self.token_data[token_address]['ticker']}: Size of a transfer to {wallet_to} is lower than {min_cached_size} for cached price")
                return 0

    async def _address_filter(self, event_type:str, event_data:dict):
        """
        Filter events and get address labels.
        - Filters out exchange self-transfers (same exchange in from and to)
        - Returns address labels for display
        """
        # Check for exchange self-transfers
        if self.event_filter.is_exchange_self_transfer(event_data):
            return None
        
        # Get address labels for display
        filter_names = self.event_filter.get_filter_names(event_data)

        return {
            "from_names": filter_names.get('from_names', []),
            "to_names": filter_names.get('to_names', [])
        }

    async def _filter_event(self, tx_hash: str, token_address: str, event_type:str, event_data:dict):

        custom_rule = self.custom_rules.get(self.chain_name, {}).get(token_address, {}).get("event_rules",{}).get(event_type)
        auto_open = False
        address_filter = {"from_names": [], "to_names": []}
        usd_size = 0
        
        if self.chain_name == 'BSC':
            alpha_signal = await self._detect_alpha(token_address, event_data)
            if alpha_signal: 
                return alpha_signal

        if custom_rule: 
            auto_open = True
            message_tier = "Custom event"
            custom_token_data = self.custom_rules.get(self.chain_name, {}).get(token_address, {}).get("token_data",{})
            token_decimals = custom_token_data['decimals']
            token_amount_in_event = event_data['total']/10**token_decimals
            circ_supply = custom_token_data['circulating_supply']
            ticker = custom_token_data.get('ticker')
            trade_direction = custom_rule.get('direction')

            if custom_rule.get('custom_event_name'):
                event_type = custom_rule.get('custom_event_name')

            from_filter = custom_rule.get('from')
            to_filter = custom_rule.get('to')
    
            if from_filter or to_filter:
                _from = False
                _to = False
                for transfer in event_data['transfers']:
                    if from_filter and transfer['from'] in from_filter:
                        _from = True
                    if to_filter and transfer['to'] in to_filter:
                        _to = True
                if (from_filter and not _from) or (to_filter and not _to):
                    return {}

            supply_percent_filter = custom_rule.get('supply_percent')
            supply_percent_in_action = token_amount_in_event / circ_supply
            if supply_percent_in_action < supply_percent_filter:
                return {}

        else: 
            address_filter = await self._address_filter(event_type, event_data)
            if address_filter is None:
                return {}
            
            token_decimals = self.token_data[token_address]['decimals']
            token_amount_in_event = event_data['total']/10**token_decimals
            circ_supply = self.token_data[token_address]['circulating_supply']
            if circ_supply == 0:
                circ_supply = self.token_data[token_address]['total_supply']
            ticker = self.token_data[token_address]['ticker'] 
            trade_direction = self._get_event_trade_direction(event_type)

            supply_percent_in_action = token_amount_in_event / circ_supply
            event_config = self._get_event_config(event_type,supply_percent_in_action)

            if not event_config: #not supply filter check usd based filter
                usd_size = await self._check_usd_size_transfer(token_address, event_type, event_data, MIN_PARSED_PRICE_SIZE_TO_CHECK, "0x0...000")
                event_type = "usd_based_transfer"
                usd_based_config = self._get_event_config(event_type, token_amount_in_event, usd_size)
                if not usd_based_config:
                    return {}
                # usd_based_transfer requires address name matches
                if not (address_filter['from_names'] or address_filter['to_names']):
                    return {}
                event_config = usd_based_config
            
            # Signature blacklist check - only after supply/USD filter passes
            if self.event_filter.has_signature_filters(event_type):
                try:
                    receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                    sig_matches = self.event_filter.check_signatures_in_receipt(event_type, receipt)
                    if sig_matches:
                        return {}
                except Exception as e:
                    self.logger.error(f"Error fetching receipt for signature check: {e}")
            
            auto_open = event_config.get('auto_open')
            message_tier = event_config.get('message_tier') 

        from_addresses = [t['from'] for t in event_data.get('transfers', [])]
        to_addresses = [t['to'] for t in event_data.get('transfers', [])]
        unique_from = list(set(from_addresses))
        unique_to = list(set(to_addresses))
            
        signal = {
            "direction": trade_direction,
            "ticker": ticker,
            "contract": token_address,
            "event_type": event_type,
            "supply_percent": supply_percent_in_action,
            "auto_open": auto_open, 
            "message_tier": message_tier,
            "token_amount": token_amount_in_event,
            "usd_amount": usd_size,
            "from_addresses": unique_from,
            "to_addresses": unique_to
        }
        
        if address_filter['from_names'] or address_filter['to_names']:
            signal["filter_matches"] = {
                "from": address_filter['from_names'],
                "to": address_filter['to_names']
            }
        
        return signal

    async def detect(self,tx_hash:str, events:dict):
        """events: {
        
            "token_address": {
                "event_type1": {
                    "total": 123,
                    "transfers" [
                        {
                            "from": "0x123",
                            "to": "0x456",
                            "amount": 123
                        }
                    ]
                },
                "event_type2": ...
            },
            "token_address2": ...
        }
                
        returns: dict: {
            chain_name: str,
            tx_hash: str,
            signals: list[
                {
                   "direction": Literal['long', 'short'],
                    "ticker": str,
                    "contract": str,
                    "event_type": Literal['mint', 'burn', 'transfer', 'claim'],
                    "supply_percent": float,
                    
                }
            ]
        }
            
        """
        
        signals = {
            "chain_name": self.chain_name,
            "tx_hash": tx_hash,
            "signals": []
        }
        for token_address, token_events in events.items():
            for event_type, event_data in token_events.items():
                signal = await self._filter_event(tx_hash, token_address, event_type, event_data)
                if signal:
                    signals['signals'].append(signal)
        
        return signals