from tg_client import TelegramClient

from typing import Dict
from config import CHAIN_NAMES
from typing import Literal
from .log_parser import EventParser
from config import FILTER_CONFIG, EVENT_TRADE_DIRECTION
from utils import Gecko, get_logger

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

    
    def _get_event_trade_direction(self, event_type:str) -> Literal['long', 'short']: 
        return EVENT_TRADE_DIRECTION.get(event_type, '')

    def _get_event_config(self, event_type:str, supply_percent_in_action:float) -> dict:
        for config in FILTER_CONFIG[event_type]:
            if not config['enabled']:
                continue 
            if config['min_supply_percent'] <= supply_percent_in_action < config['max_supply_percent']:
                return config
        return {}

    def update_custom_rules(self, custom_rules: dict):
        self.custom_rules = custom_rules

    def _filter_event(self, token_address: str, event_type:str, event_data:dict):

        custom_rule = self.custom_rules.get(self.chain_name, {}).get(token_address, {}).get("event_rules",{}).get(event_type)
        auto_open = False

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
            token_decimals = self.token_data[token_address]['decimals']
            token_amount_in_event = event_data['total']/10**token_decimals
            circ_supply = self.token_data[token_address]['circulating_supply']
            if circ_supply == 0:
                circ_supply = self.token_data[token_address]['total_supply']
            ticker = self.token_data[token_address]['ticker'] 
            trade_direction = self._get_event_trade_direction(event_type)

            supply_percent_in_action = token_amount_in_event / circ_supply
            event_config = self._get_event_config(event_type,supply_percent_in_action)
            if not event_config:
                return {}
            auto_open = event_config.get('auto_open')
            message_tier = event_config.get('message_tier') 
            
            
        
        return {
            "direction": trade_direction,
            "ticker": ticker,
            "contract": token_address,
            "event_type": event_type,
            "supply_percent": supply_percent_in_action,
            "auto_open": auto_open, 
            "message_tier": message_tier
        }

        

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
                signal = self._filter_event(token_address, event_type, event_data)
                if signal:
                    signals['signals'].append(signal)
        
        return signals
        