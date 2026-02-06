from .log_parser import EventParser
from web3 import AsyncWeb3
from typing import Callable, Literal
from config import CHAIN_NAMES, WS_RPC, RECONNECT_ATTEMPTS
from utils import get_logger
import asyncio
import json
import websockets
from tg_client import TelegramClient
import traceback
import time

class BlockListenerEVM:

    def __init__(
        self, 
        tg_client:TelegramClient, 
        chain_name:Literal[*CHAIN_NAMES], 
        token_address_list: list, 
        target_events: list,
    ):
        
        self.w3 = AsyncWeb3(AsyncWeb3.WebSocketProvider(WS_RPC[chain_name]))
        self._ws_connection_check_interval = 5
        self.token_address_list = token_address_list
        self.target_events = target_events
        self.chain_name = chain_name
        self.tg_client = tg_client
        self.logger = get_logger(f'{chain_name}')
        self._max_addresses_per_request = 500
        
    @classmethod
    async def create(
        cls,
        tg_client: TelegramClient,
        chain_name: Literal[*CHAIN_NAMES],
        token_address_list: list,
        target_events: list,
    ):
        instance = cls(tg_client, chain_name, token_address_list, target_events)
        await instance.w3.provider.connect()
        asyncio.create_task(instance._ws_connection_checker())
        return instance

    def update_token_address_list(self, token_address_list: list):
        self.token_address_list = token_address_list

    async def _ws_connection_checker(self):
        
        while True:
            try:
                if not await self.w3.provider.is_connected():
                    await self.w3.provider.connect()
                    self.logger.info(f"WebSocket connection reestablished")
                await asyncio.sleep(self._ws_connection_check_interval)
            except Exception as e:
                self.logger.error(f"WebSocket connection error: {str(e)}")
                await self.tg_client.send_error_alert(
                    "RPC WEBSCOKET DISCONNECTED",
                    f"{self.chain_name} WebSocket connection error: {str(e)}",
                )
                await asyncio.sleep(self._ws_connection_check_interval)
    
    async def _get_logs_for_block(self, block_num: int) -> list:
        """Fetch logs for a single block, batching by address to avoid message size limits."""
        all_logs = []
        for i in range(0, len(self.token_address_list), self._max_addresses_per_request):
            address_batch = self.token_address_list[i:i + self._max_addresses_per_request]
            payload = {
                "fromBlock": hex(block_num),
                "toBlock": hex(block_num),
                "address": address_batch,
                "topics": self.target_events,
            }
            logs = await self.w3.eth.get_logs(payload)
            all_logs.extend(logs)
        return all_logs
    
    async def subscribe_new_blocks(self, callback:Callable):
        """
        Подписаться на новые блоки через WebSocket
        Для каждого нового блока вызывает callback
        передает в callback 
        {
            'token': token_address,
            'from': from_address,
            'to': to_address,
            'amount': value
        }
        """
        last_block = await self.w3.eth.block_number - 1
        self.logger.info(f"Starting subscription from block {last_block + 1}")
        
        ws_url = WS_RPC[self.chain_name]
        reconnect_delay = 5
        reconnect_attempts = 0
        while True:
            try:
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=30) as ws:
                    reconnect_attempts = 0
                    subscribe_msg = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": ["newHeads"]
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    
                    sub_response = await ws.recv()
                    sub_data = json.loads(sub_response)
                    sub_id = sub_data.get("result")
                    self.logger.info(f"Subscribed to newHeads: {sub_id}")

                    while True:
                        message = await ws.recv()
                        data = json.loads(message)
                        
                        if data.get("method") == "eth_subscription":
                            params = data.get("params", {})
                            result = params.get("result", {})
                            
                            if "number" in result:
                                current_block = int(result["number"], 16)
                                
                                t1 = time.perf_counter()

                                if current_block > last_block:
                                    # Process blocks one at a time to avoid message too big errors
                                    if current_block - last_block > 5:
                                        current_block = last_block + 5
                                    for block_num in range(last_block + 1, current_block + 1):
                                        try:
                                            all_logs = await self._get_logs_for_block(block_num)
                                            all_txs = {}
                                            for log in all_logs:
                                                tx_hash = "0x" + log['transactionHash'].hex()
                                                if tx_hash not in all_txs:
                                                    all_txs[tx_hash] = []
                                                all_txs[tx_hash].append(log)
                                            t2 = time.perf_counter()
                                            self.logger.debug(f"got data for block {block_num} in {(t2-t1)*1000:.2f}ms")
                                            for tx_hash, tx_logs in all_txs.items():
                                                events = EventParser.parse_tx_token_events_from_logs(tx_logs)
                                                if events:
                                                    asyncio.create_task(callback(tx_hash, events))
                                            last_block = block_num
                                        except Exception as e:
                                            self.logger.error(f"Error processing block {block_num}: {str(e)}")
                                            if "message too big" in str(e):
                                                self.logger.warning(f"Skipping block {block_num} due to message size")
                                                last_block = block_num
                                            await asyncio.sleep(0.1)
                                

            except (websockets.ConnectionClosed, websockets.ConnectionClosedError, ConnectionResetError) as e:
                self.logger.warning(f"WebSocket disconnected: {str(e)}. Reconnecting in {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_attempts += 1
                if reconnect_attempts >= RECONNECT_ATTEMPTS:
                    self.logger.error(f"Max reconnect attempts reached for {self.chain_name}")
                    await self.tg_client.send_error_alert(
                        "BLOCK SUBSCRIPTION ERROR",
                        f"{self.chain_name} Max reconnect attempts reached"
                    )
                    break
            except Exception as e:
                self.logger.error(f"Error in subscribe_new_blocks: {str(e)}")
                await self.tg_client.send_error_alert(
                    "BLOCK SUBSCRIPTION ERROR",
                    f"{self.chain_name} Error: {str(e)}"
                )
                await asyncio.sleep(reconnect_delay)

      
        
        


        

        




    