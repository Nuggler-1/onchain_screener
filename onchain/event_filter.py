import os
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from config import EXCHANGE_NAMES_FOR_SELF_TRANSFER_FILTER


class EventFilter:
    """Event filter using dict for address label lookups and exchange self-transfer detection"""
    
    def __init__(self, filters_base_path: str = 'database/filters'):
        self.filters_base_path = filters_base_path
        self.filters = {}
        self.address_labels: Dict[str, str] = {}
        self.exchange_names = [name.lower() for name in EXCHANGE_NAMES_FOR_SELF_TRANSFER_FILTER]
        self._ensure_directories()
        self.reload_filters()
    
    def _ensure_directories(self):
        event_types = ['transfer', 'mint', 'burn']
        for event_type in event_types:
            event_dir = os.path.join(self.filters_base_path, event_type)
            os.makedirs(event_dir, exist_ok=True)
            
            for filter_file in ['blacklist_signatures.txt']:
                file_path = os.path.join(event_dir, filter_file)
                if not os.path.exists(file_path):
                    Path(file_path).touch()
    
    def _load_filter_file(self, file_path: str) -> Dict[str, str]:
        result = {}
        if not os.path.exists(file_path):
            return result
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    if ':' in line:
                        key, name = line.split(':', 1)
                        key = key.strip().lower()
                        name = name.strip()
                        if key:
                            result[key] = name
        except Exception as e:
            print(f"Error loading filter file {file_path}: {e}")
        
        return result
    
    def reload_filters(self):
        event_types = ['transfer', 'mint', 'burn']
        
        for event_type in event_types:
            event_dir = os.path.join(self.filters_base_path, event_type)
            
            self.filters[event_type] = {
                'blacklist_signatures': self._load_filter_file(
                    os.path.join(event_dir, 'blacklist_signatures.txt')
                )
            }
        
        # Load address labels
        labels_path = os.path.join(self.filters_base_path, 'address_labels.txt')
        self.address_labels = self._load_filter_file(labels_path)
    
    def get_address_label(self, address: str) -> Optional[str]:
        """Get label for an address from dict"""
        return self.address_labels.get(address.lower())
    
    def get_labels_for_event(self, event_data: dict) -> Dict[str, Dict[str, Optional[str]]]:
        """
        Get labels for all from/to addresses in an event.
        Returns: {'from': {addr: label}, 'to': {addr: label}}
        """
        from_labels = {}
        to_labels = {}
        
        for transfer in event_data.get('transfers', []):
            from_addr = transfer.get('from', '')
            to_addr = transfer.get('to', '')
            if from_addr:
                from_labels[from_addr] = self.get_address_label(from_addr)
            if to_addr:
                to_labels[to_addr] = self.get_address_label(to_addr)
        
        return {
            'from': from_labels,
            'to': to_labels
        }
    
    def _extract_exchange_name(self, label: str) -> Optional[str]:
        """Extract exchange name from label if it matches any known exchange"""
        if not label:
            return None
        label_lower = label.lower()
        for exchange in self.exchange_names:
            if exchange in label_lower:
                return exchange
        return None
    
    def is_exchange_self_transfer(self, event_data: dict) -> bool:
        """
        Check if event is an exchange self-transfer.
        Returns True if any from address and to address share the same exchange label.
        """
        labels_info = self.get_labels_for_event(event_data)
        
        from_exchanges = set()
        for addr, label in labels_info['from'].items():
            exchange = self._extract_exchange_name(label)
            if exchange:
                from_exchanges.add(exchange)
        
        for addr, label in labels_info['to'].items():
            exchange = self._extract_exchange_name(label)
            if exchange and exchange in from_exchanges:
                return True
        
        return False
    
    def has_signature_filters(self, event_type: str) -> bool:
        if event_type not in self.filters:
            return False
        
        event_filters = self.filters[event_type]
        return len(event_filters['blacklist_signatures']) > 0
    
    def check_signatures_in_receipt(self, event_type: str, receipt) -> List[Tuple[str, str]]:
        if event_type not in self.filters:
            return []
        
        event_filters = self.filters[event_type]
        blacklist_sigs = event_filters['blacklist_signatures']
        
        if not blacklist_sigs:
            return []
        
        matches = []
        
        for log in receipt.get('logs', []):
            if len(log.get('topics', [])) == 0:
                continue
            
            topic0 = log['topics'][0].hex()
            if topic0.startswith('0x'):
                topic0 = topic0[2:]
            topic0_lower = topic0.lower()
            
            if topic0_lower in blacklist_sigs:
                matches.append((topic0, blacklist_sigs[topic0_lower]))
        
        return matches
    
    def get_filter_names(self, event_data: dict) -> Dict[str, Dict[str, str]]:
        """Get from/to address->name mappings for display in alerts"""
        labels_info = self.get_labels_for_event(event_data)
        
        # Return address->name dicts (only addresses with labels)
        from_names = {addr: label for addr, label in labels_info['from'].items() if label}
        to_names = {addr: label for addr, label in labels_info['to'].items() if label}
        
        return {
            'from_names': from_names,
            'to_names': to_names
        }
