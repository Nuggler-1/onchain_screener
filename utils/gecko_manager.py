from curl_cffi.requests import AsyncSession
from config import GECKO_API_KEY, GECKO_CHAIN_NAMES, CHAIN_NAMES
from typing import Literal
from .http_client import HttpClient
from utils import get_logger
import json
class Gecko(HttpClient): 
    def __init__(self):
        super().__init__(base_url="https://pro-api.coingecko.com/api/v3/", headers={"x-cg-pro-api-key": GECKO_API_KEY})
        self.logger = get_logger("GECKO")

    def _chain_name_to_gecko(self, chain_name: Literal[*CHAIN_NAMES]):
        return GECKO_CHAIN_NAMES[chain_name]

    async def get_token_price_simple(self, chain_name: Literal[*CHAIN_NAMES], token_address: str) -> dict:
        url = f"simple/token_price/{self._chain_name_to_gecko(chain_name)}?contract_addresses={token_address}&vs_currencies=usd"
        data = await self.get_json(url)
        price = data.get(token_address.lower(), {}).get("usd", 0)
        if price is None or price == 0:
            self.logger.warning(f"Token price for {token_address} not found: {json.dumps(data, indent=4)}")
            return 0
        return float(price)
    
    async def get_token_data_for_message(self, chain_name: Literal[*CHAIN_NAMES], token_address: str) -> dict:
        url = f"onchain/networks/{self._chain_name_to_gecko(chain_name)}/tokens/{token_address}"
        data = await self.get_json(url)
        attributes = data.get('data', {}).get('attributes', {})
        if not attributes:
            return {}
        mcap = attributes.get("market_cap_usd") or 0
        volume = (attributes.get("volume_usd") or {}).get("h24") or 0
        price = attributes.get("price_usd") or 0
        return {"price": float(price), "mcap": float(mcap), "volume": float(volume)}