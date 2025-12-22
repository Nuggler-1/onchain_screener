from config import CUSTOM_RULES_PATH, SUPPLY_DATA_PATH, CHAIN_NAMES
from typing import Literal
import json

def get_full_token_list(chain_name: Literal[*CHAIN_NAMES]) -> list:
    """Get list of token addresses for a chain from both supply data and custom rules"""
    token_list = []
    chain_name = chain_name.upper()
    
    with open(SUPPLY_DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if len(data) != 2:
            return []
        else: 
            data = data[1]
        chain_data = data.get(chain_name, {})
        for token_address in chain_data.keys():
            token_list.append(token_address)

    with open(CUSTOM_RULES_PATH, 'r', encoding='utf-8') as f:
        custom_rules = json.load(f)
        chain_rules = custom_rules.get(chain_name, {})
        for token_address in chain_rules.keys():
            if token_address not in token_list:
                token_list.append(token_address)
    
    return token_list