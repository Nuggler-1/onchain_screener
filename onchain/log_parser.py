from typing import Optional, Dict
from datetime import datetime
from web3 import Web3
from web3.types import TxReceipt
from .consts import ZERO_ADDRESS, BURN_ADDRESS

class EventParser:

    @staticmethod
    def parse_tx_token_events_from_logs(transfer_logs:list) -> dict: 

        """
        returns: 
        {
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
        """

        parsed_events = []
        for log in transfer_logs:
            event = EventParser.parse_transfer(log)
            if not event:
                continue
            event_type = "transfer"
            if EventParser.is_mint_event(event):
                event_type = "mint"
            if EventParser.is_burn_event(event):
                event_type = "burn" 
            event['event_type'] = event_type
            parsed_events.append(event)

        # Calculate net flow per address per token to handle chains (A->B->C) and roundtrips
        # Track balance changes: negative = outflow, positive = inflow
        token_balances = {}  # {token: {address: net_balance}}
        for event in parsed_events:
            if event['event_type'] != 'transfer':
                continue
            token = event['token_address']
            from_addr = event['from']
            to_addr = event['to']
            amount = event['amount']
            
            if token not in token_balances:
                token_balances[token] = {}
            if from_addr not in token_balances[token]:
                token_balances[token][from_addr] = 0
            if to_addr not in token_balances[token]:
                token_balances[token][to_addr] = 0
            
            token_balances[token][from_addr] -= amount  # outflow
            token_balances[token][to_addr] += amount    # inflow

        # Account for burn events: if 'from' address is in token_balances, add to outflow
        for event in parsed_events:
            if event['event_type'] != 'burn':
                continue
            token = event['token_address']
            from_addr = event['from']
            amount = event['amount']
            
            if token in token_balances and from_addr in token_balances[token]:
                token_balances[token][from_addr] -= amount  # burn is outflow

        # Net transfer amount = sum of all outflows (negative balances) = sum of all inflows (positive balances)
        token_net_transfers = {}
        for token, balances in token_balances.items():
            # Sum of positive balances (or abs of negative) gives net transfer
            token_net_transfers[token] = sum(b for b in balances.values() if b > 0)

        token_events = {}
        for event in parsed_events:
            event_token = event.get('token_address')
            event_type = event.get('event_type')
            
            if event_token not in token_events:
                token_events[event_token] = {
                    'mint': {'total': 0, 'transfers': []}, 
                    'burn': {'total': 0, 'transfers': []}, 
                    'transfer': {'total': 0, 'transfers': []},
                }

            if event_type == 'transfer':
                if event_token in token_net_transfers:
                    token_events[event_token]['transfer']['total'] = token_net_transfers.pop(event_token)
            else:
                token_events[event_token][event_type]['total'] += event['amount']
            
            token_events[event_token][event_type]['transfers'].append({
                'from': event['from'],
                'to': event['to'],
                'amount': event['amount']
            })
                
        return token_events

    @staticmethod
    def parse_transfer(log):
        try:
            from_address = '0x' + log['topics'][1].hex()[-40:]  # берём последние 40 символов (20 байт)
            to_address = '0x' + log['topics'][2].hex()[-40:]
            value = int(log['data'].hex(), 16)
            token_address = log['address']
           # tx_hash = log['transactionHash'].hex()
            return {
                    'token_address': token_address,
                    'from': from_address,
                    'to': to_address,
                    'amount': value,
                    #'tx_hash': tx_hash
                }
        except:
            return None

    @staticmethod
    def is_mint_event(transfer:dict):
        return transfer.get('from') == ZERO_ADDRESS
        
    @staticmethod
    def is_burn_event(transfer:dict):
        return transfer.get('to') in [ZERO_ADDRESS, BURN_ADDRESS]

    @staticmethod
    def parse_transfer_events_from_receipt(receipt: TxReceipt) -> list[dict]:
        transfers = []
    
        for log in receipt['logs']:
            # Проверяем, это ли Transfer событие ( 0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef)
            if len(log['topics']) >= 3:
                topic0 = log['topics'][0].hex()
                if topic0 == 'ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef':
                    event = EventParser.parse_transfer(log)
                    if event:
                        transfers.append(event)
    
        return transfers

    @staticmethod
    def parse_mint_event_from_receipt(receipt:TxReceipt) -> list[dict] :
        transfers = EventParser.parse_transfer_events_from_receipt(receipt)
        mints = []
        for transfer in transfers:
            if EventParser.is_mint_event(transfer):
                mints.append(transfer)
        return mints

    @staticmethod
    def parse_burn_event_from_receipt(receipt:TxReceipt) -> list[dict]: 
        transfers = EventParser.parse_transfer_events_from_receipt(receipt)
        burns = []
        for transfer in transfers: 
            if EventParser.is_burn_event(transfer):
                burns.append(transfer)
        return burns