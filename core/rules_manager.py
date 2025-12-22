import json
from typing import Dict, Literal
from config import SUPPLY_DATA_PATH, CUSTOM_RULES_PATH, CHAIN_NAMES
from utils import get_logger

class RulesManager:
    def __init__(self):
        self.logger = get_logger("RULES_MANAGER")
        self.token_data = self._load_token_data()
        self.custom_rules = self._load_custom_rules()

    def _load_token_data(self):
        try:
            with open(SUPPLY_DATA_PATH, 'r', encoding='utf-8') as f:
                raw = json.load(f)
                if isinstance(raw, list) and len(raw) > 1:
                    return raw[1]
                else:
                    return {}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.error(f"Failed to load token_data.json: {e}")
            return {}

    def _load_custom_rules(self):
        try:
            with open(CUSTOM_RULES_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse custom_rules.json: {e}")
            return {}

    def _save_custom_rules(self):
        with open(CUSTOM_RULES_PATH, 'w') as f:
            json.dump(self.custom_rules, f, indent=4)

    def get_token_data(self, token_address: str) -> Dict:
        token_data = self._load_token_data()
        for chain_name, tokens in token_data.items():
            for addr, data in tokens.items():
                if addr == token_address:
                    return {
                        "ticker": data.get("ticker", ""),
                        "chain": chain_name,
                        "decimals": data.get("decimals"),
                        "circulating_supply": data.get("circulating_supply"),
                        "supply": data.get("total_supply"),
                    }
        return {}

    def add_rule(
        self,
        chain: str,
        token_address: str,
        token_data: Dict,
        event_type: Literal["mint", "transfer", "burn"],
        rule: Dict,
    ) -> bool:
        chain = chain.upper()
        if chain not in self.custom_rules:
            self.custom_rules[chain] = {}
        
        if token_address not in self.custom_rules[chain]:
            self.custom_rules[chain][token_address] = {
                "token_data": token_data,
                "event_rules": {}
            }
        
        self.custom_rules[chain][token_address]["token_data"] = token_data
        self.custom_rules[chain][token_address]["event_rules"][event_type] = rule
        
        self._save_custom_rules()
        self.logger.info(f"Added {event_type} rule for {token_address} on {chain}")
        return True

    def remove_rule(
        self,
        chain: str,
        token_address: str,
        event_type: Literal["mint", "transfer", "burn"],
    ) -> bool:
        chain = chain.upper()
        if chain not in self.custom_rules:
            self.logger.warning(f"Chain {chain} not found in custom rules")
            return False
        
        if token_address not in self.custom_rules[chain]:
            self.logger.warning(f"Token {token_address} not found in custom rules for {chain}")
            return False
        
        event_rules = self.custom_rules[chain][token_address].get("event_rules", {})
        if event_type not in event_rules:
            self.logger.warning(f"Rule {event_type} not found for {token_address}")
            return False
        
        del event_rules[event_type]
        
        if not event_rules:
            del self.custom_rules[chain][token_address]
            self.logger.info(f"Removed token {token_address} from {chain} (no rules left)")
            if not self.custom_rules[chain]:
                del self.custom_rules[chain]
        else:
            self.logger.info(f"Removed {event_type} rule for {token_address} on {chain}")
        
        self._save_custom_rules()
        return True

    def get_rules(self, chain: str, token_address: str) -> Dict:
        self._load_custom_rules()
        chain = chain.upper()
        return self.custom_rules.get(chain, {}).get(token_address, {})

    def get_chain_rules(self, chain: str) -> Dict:
        self._load_custom_rules()
        chain = chain.upper()
        return self.custom_rules.get(chain, {})

    def get_all_rules(self) -> Dict:
        self._load_custom_rules()
        return self.custom_rules

    def get_all_rules_flat(self) -> list:
        """Returns a flat list of (chain, token_address, data) tuples for UI display"""
        self._load_custom_rules()
        result = []
        for chain, tokens in self.custom_rules.items():
            for token_address, data in tokens.items():
                result.append((chain, token_address, data))
        return result

    def remove_token(self, chain: str, token_address: str) -> bool:
        chain = chain.upper()
        if chain not in self.custom_rules:
            self.logger.warning(f"Chain {chain} not found in custom rules")
            return False
        
        if token_address not in self.custom_rules[chain]:
            self.logger.warning(f"Token {token_address} not found in custom rules for {chain}")
            return False
        
        del self.custom_rules[chain][token_address]
        if not self.custom_rules[chain]:
            del self.custom_rules[chain]
        self._save_custom_rules()
        self.logger.info(f"Removed all rules for {token_address} on {chain}")
        return True

    def update_token_data(self, chain: str, token_address: str, field: str, value) -> bool:
        chain = chain.upper()
        if chain not in self.custom_rules:
            self.logger.warning(f"Chain {chain} not found in custom rules")
            return False
        
        if token_address not in self.custom_rules[chain]:
            self.logger.warning(f"Token {token_address} not found in custom rules for {chain}")
            return False
        
        if "token_data" not in self.custom_rules[chain][token_address]:
            self.custom_rules[chain][token_address]["token_data"] = {}
        
        self.custom_rules[chain][token_address]["token_data"][field] = value
        self._save_custom_rules()
        self.logger.info(f"Updated {field} for {token_address} on {chain}")
        return True

    def reload(self):
        self._load_token_data()
        self._load_custom_rules()
