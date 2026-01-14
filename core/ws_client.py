import asyncio
import json
import websockets
from config import SIGNAL_WS_URL, RECONNECT_ATTEMPTS, RECONNECT_DELAY
from utils import get_logger
from onchain import BlockListenerEVM
from onchain import EventDetectorEVM
from tg_client import TelegramClient


class WebsocketClient:
    def __init__(self, tg_client: TelegramClient):
        self.detectors: dict[str, EventDetectorEVM] = {}
        self.listeners: dict[str, BlockListenerEVM] = {}
        self.logger = get_logger("WS_CLIENT")
        self.tg_client = tg_client
        self.ws = None
        self._connected = False
        self._message_queue: asyncio.Queue = asyncio.Queue()

    def add_listener(self, chain_name: str, listener: BlockListenerEVM):
        self.listeners[chain_name] = listener
        self.logger.info(f"Added listener for {chain_name}")

    def add_detector(self, chain_name: str, detector: EventDetectorEVM):
        self.detectors[chain_name] = detector
        self.logger.info(f"Added detector for {chain_name}")

    async def _send_signal(self, message: dict):
        """Queue a message to be sent to the WS server"""
        await self._message_queue.put(message)
        self.logger.info(f"Signal put to queue: {message}")

    async def _sender_loop(self):
        """Background task that sends queued messages to the WS server"""
        while True:
            message = await self._message_queue.get()
            if self._connected and self.ws:
                try:
                    await self.ws.send(json.dumps(message))
                    self.logger.success(f"Signal sent to server")
                except websockets.ConnectionClosed:
                    self.logger.warning("Connection closed while sending, message dropped")
                    self._connected = False
                except Exception as e:
                    self.logger.error(f"Error sending message: {e}")

    async def _receiver_loop(self):
        """Background task that receives messages from WS server and handles ping/pong"""
        while True:
            if not self._connected or not self.ws:
                await asyncio.sleep(0.1)
                continue
            try:
                message = await self.ws.recv()
                data = json.loads(message)
                
                if data.get('type') == 'ping':
                    await self.ws.send(json.dumps({'type': 'pong'}))
                    self.logger.success("Received ping, sent pong")
                    
            except websockets.ConnectionClosed:
                self.logger.warning("Connection closed in receiver loop")
                self._connected = False
            except json.JSONDecodeError:
                self.logger.warning(f"Received non-JSON message: {message}")
            except Exception as e:
                self.logger.error(f"Error in receiver loop: {e}")

    async def _connect(self):
        """Connect to the WS server with retry logic"""
        for attempt in range(RECONNECT_ATTEMPTS):
            try:
                self.logger.info(f"Connecting to WS server: {SIGNAL_WS_URL}")
                self.ws = await websockets.connect(SIGNAL_WS_URL)
                self._connected = True
                self.logger.success(f"Connected to WS server: {SIGNAL_WS_URL}")
                attempt = 0
                return True
            except Exception as e:
                self.logger.warning(f"Connection attempt {attempt + 1}/{RECONNECT_ATTEMPTS} failed: {e}")
                if attempt < RECONNECT_ATTEMPTS - 1:
                    await asyncio.sleep(RECONNECT_DELAY)
        
        self.logger.error(f"Failed to connect to WS server after {RECONNECT_ATTEMPTS} attempts")
        return False

    async def _connection_loop(self):
        """Maintain connection to the WS server"""
        while True:
            if not self._connected:
                connected = await self._connect()
                if connected:
                    await self.ws.wait_closed()
                    self._connected = False
                else: 
                    self.tg_client.send_error_alert(
                        f"Failed to connect to controller WS server after {RECONNECT_ATTEMPTS} attempts",
                        "Reconnect failed"
                    )
                    return
            await asyncio.sleep(1)

    def _create_callback(self, chain_name: str):
        detector = self.detectors[chain_name]
        
        async def callback(tx_hash: str, events: dict):
            try:
                signals = await detector.detect(tx_hash, events)
                ws_msg = {
                    'service_type': 'onchain_screener',
                    'signals': []
                }
                if signals.get('signals'):
                    for signal in signals.get('signals'):
                        if signal.get('auto_open'):
                            ws_msg['signals'].append(signal)
                if ws_msg['signals']:
                    self.logger.info(f"Auto open signals detected: {[(signal['ticker'], signal['event_type']) for signal in ws_msg['signals']]}")
                    await self._send_signal(ws_msg)

                for signal in signals.get('signals'):
                    self.logger.info(f"Signal detected: {signal['ticker']} {signal['event_type']} on {chain_name}")
                    signal['chain'] = chain_name.lower()
                    signal['tx_hash'] = tx_hash
                    await self.tg_client.send_alert(signal)
                return
            except Exception as e:
                self.logger.error(f"Error in callback for {chain_name}: {e}")
        
        return callback

    async def _run_listener(self, chain_name: str):
        if chain_name not in self.detectors:
            self.logger.error(f"No detector for {chain_name}")
            return
        if chain_name not in self.listeners:
            self.logger.error(f"No listener for {chain_name}")
            return
        
        callback = self._create_callback(chain_name)
        self.logger.info(f"Starting block listener for {chain_name}")
        await self.listeners[chain_name].subscribe_new_blocks(callback)

    async def start(self):
        
        if not await self._connect():
            self.logger.error(f"Failed to connect to WS server, exiting")
            self.tg_client.send_error_alert(
                f"Failed to connect to controller WS server after {RECONNECT_ATTEMPTS} attempts",
                "WS connection failed"
            )
            return
        
        # Start receiver loop after initial connection
        asyncio.create_task(self._receiver_loop())
        
        connection_task = asyncio.create_task(self._connection_loop())
        sender_task = asyncio.create_task(self._sender_loop())
        
        listener_tasks = [
            asyncio.create_task(self._run_listener(chain))
            for chain in self.listeners.keys()
        ]

        await asyncio.gather(connection_task, sender_task, *listener_tasks)
