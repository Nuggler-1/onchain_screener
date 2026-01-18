from typing import Callable
from config import (
    CMC_PLATFORM_NAMES,
    CMC_API_KEY,
    PARSED_DATA_CHECK_DELAY_DAYS, 
    SUPPLY_DATA_PATH, 
    BANNED_PATH,
    CACHE_UPDATE_BATCH_SIZE,
    CHAIN_NAMES,
    FORCE_UPDATE_ON_START,
    CMC_SEARCH_LISTS,
    WS_RPC, 
    REQUEST_RETRY,
    MIN_MCAP, 
    MIN_VOLUME
)
from utils import Gecko
from curl_cffi.requests import AsyncSession
from web3 import Web3
from web3 import AsyncWeb3
import json
from utils import get_logger
import asyncio
import os
import time
from onchain.consts import DEX_ROUTER_DATA, erc20_abi
from datetime import datetime, timedelta
import ujson
import base58

class HelperSOL: 

    def __init__(self,):
        self.logger = get_logger("PARSER")

    def _is_valid_solana_address(self, address: str) -> bool:
        """Validate if a string is a valid Solana Base58 address"""
        if not address or not isinstance(address, str):
            return False
        try:
            # Solana addresses are 32-44 characters in Base58
            if len(address) < 32 or len(address) > 44:
                return False
            # Try to decode as base58
            decoded = base58.b58decode(address)
            # Solana public keys are 32 bytes
            if len(decoded) != 32:
                return False
            return True
        except Exception:
            return False
        

class HelperEVM:

    def __init__(self):
        self.logger = get_logger("PARSER")
        self.w3_providers = {
            chain_name: AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(WS_RPC[chain_name])) for chain_name in CHAIN_NAMES if chain_name != 'SOLANA'
        }

    async def _disconnect_all_providers(self):
        for provider in self.w3_providers.values():
            if not provider.provider.is_connected():
                continue
            await provider.provider.disconnect()

    async def _connect_all_providers(self):
        for provider in self.w3_providers.values():
            if provider.provider.is_connected():
                continue
            await provider.provider.connect()
    
    async def _get_token_decimals(self,token_address:str, chain_name: str):
        try:
            w3= self.w3_providers.get(chain_name)
            token_contract = w3.eth.contract(address=token_address, abi=erc20_abi)
            decimals = await token_contract.functions.decimals().call()
            return decimals
        except Exception as e:
            self.logger.error(f"Error getting token decimals for {token_address} on {chain_name}: {str(e)}")
            return None
    
 

class SupplyParser:

    def __init__(self):
        self.logger = get_logger("PARSER")
        self.main_token_data, self._last_update_time = self._load_token_data()
        self.helper_sol = HelperSOL()
        self.helper_evm = HelperEVM()
        self.gecko = Gecko()
        self.chain_separated_pool_dict = {}
        self._parser_task = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
            'platform': 'web',
            'Accept': 'application/json, text/plain, */*',
            'Accept-encoding': 'gzip, deflate, br',
            'Accept-language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Referer': 'https://coinmarketcap.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',

        }
    async def stop(self): 
        if self._parser_task:
            self._parser_task.cancel()
            self._parser_task = None
    
    async def _search_query(
        self, 
        range_start: int, 
        range_end: int,
        aux: str = 'circulating_supply,total_supply,self_reported_circulating_supply',
        additional_params: str = ''
        
    ):
        """additional_params - дополнительные параметры для запроса в формате key=value&key2=value2"""

        url = f'https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing?start={range_start}&limit={range_end}&convert=USD&sortBy=rank&sortType=desc&cryptoType=all&tagType=all&audited=false&aux={aux}&{additional_params}'

        async with AsyncSession() as session: 
            response = await session.get(url, headers=self.headers)
            response.raise_for_status() 
            data = response.json().get('data').get('cryptoCurrencyList')
        return data

    async def _get_cmc_quote_for_token_ticker(self,token_ticker:str): 

        url = f"https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest?symbol={token_ticker}&convert=USD"
        headers = {
            'X-CMC_PRO_API_KEY': CMC_API_KEY,
            'Accept': 'application/json'
        }
        for _ in range(REQUEST_RETRY): 
            try:
                async with AsyncSession() as session: 
                    response = await session.get(url, headers=headers)
                    response.raise_for_status()
                    data = response.json().get('data', {}).get(token_ticker.upper(), {})
                    if len(data) < 1: 
                        self.logger.error(f"No data returned from cmc")
                        return {}
                    data = data[0].get('quote', {}).get('USD',{})
                    return data
            except Exception as e:
                if _ == REQUEST_RETRY - 1: 
                    self.logger.error(f"Error getting CMC token data by ticker: {str(e)}")
                    return {}
                self.logger.warning(f"Error getting CMC token data by ticker: {str(e)}")
        
    async def _get_cmc_tokens_data_by_ids(self, token_ids: list):

        token_ids = ','.join(str(token_id) for token_id in token_ids)
        url = f'https://pro-api.coinmarketcap.com/v2/cryptocurrency/info?id={token_ids}&aux=platform'
        headers = {
            'X-CMC_PRO_API_KEY': CMC_API_KEY,
            'Accept': 'application/json'
        }
        for _ in range(REQUEST_RETRY): 
            try:
                async with AsyncSession() as session: 
                    response = await session.get(url, headers=headers)
                    response.raise_for_status()
                    data = response.json().get('data')
                    return data
            except Exception as e:
                if _ == REQUEST_RETRY - 1: 
                    self.logger.error(f"Error getting CMC tokens data by ids: {str(e)}")
                    return {}
                self.logger.warning(f"Error getting CMC tokens data by ids: {str(e)}")

    async def _get_token_id_from_search(self, token_ticker: str):

        url = f'https://api.coinmarketcap.com/gravity/v4/gravity/global-search'
        payload = { 
            "keyword": token_ticker,
            "limit": 5,
            "scene": "community"
        }
        async with AsyncSession() as session: 
            response = await session.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json().get('data',{}).get('suggestions',[])
            if not data:
                return None

            tokens = []
            for suggestion in data:
                if suggestion.get('type') == 'token':
                    tokens = suggestion.get('tokens', [])
            if not tokens:
                return None

            tk_id = 0
            for token in tokens:
                if token.get('symbol', '').lower() == token_ticker.lower():
                    tk_id = token.get('id')
                    break
            if not tk_id:
                return None
        return tk_id
        
    async def _get_supply_by_token_id(self, token_id: int):
        async with AsyncSession() as session:
            url = f"https://api.coinmarketcap.com/data-api/v3/cryptocurrency/quote/latest?id={token_id}"
            response = await session.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json().get('data',[])
            if data:
                return data[0].get('circulatingSupply', 0)
            return None

    async def _get_token_data_by_token_ticker(self, token_ticker: str):
        token_id = await self._get_token_id_from_search(token_ticker)
        if not token_id:
            self.logger.error(f'No token id found for {token_ticker}')
            return None
        supply = await self._get_supply_by_token_id(token_id)
        if not supply:
            self.logger.error(f'No supply found for {token_ticker}')
            return None
        return {
            'supply': supply,
        }

    def _load_token_data(self):
        try:
            with open(SUPPLY_DATA_PATH, 'r', encoding='utf-8') as f:
                data = json.loads(f.read())
                if len(data) != 2:
                    return None, None
                else: 
                    return data[1], datetime.fromisoformat(data[0])
        except FileNotFoundError:
            self.logger.warning(f'Token data file not found, returning empty dict')
            return None, None

    def _load_banned_list(self) -> dict:
        try:
            with open(BANNED_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {}
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _is_banned(self, token_address: str) -> bool:
        banned_dict = self._load_banned_list()
        return token_address in banned_dict

    def _should_run_parse(self):
        if self.main_token_data is None:
            return True
        
        if FORCE_UPDATE_ON_START:
            self.logger.info(f'FORCE_UPDATE_ON_START is set to True, running parse')
            return True
        
        time_since_last_run = datetime.now() - self._last_update_time
        should_run = time_since_last_run >= timedelta(days=PARSED_DATA_CHECK_DELAY_DAYS)
        
        if should_run:
            self.logger.info(f'Last parsing run was {time_since_last_run.days} days ago, running parse')
        else:
            days_until_next = PARSED_DATA_CHECK_DELAY_DAYS - time_since_last_run.days
            self.logger.info(f'Last parsing run was {time_since_last_run.days} days ago, next run in {days_until_next} days')
        
        return should_run

    async def _update_token_cache_json(self):
        self.logger.info(f'Saving main data to {SUPPLY_DATA_PATH}')

        # Создаем директорию для главного файла, если не существует
        os.makedirs(os.path.dirname(SUPPLY_DATA_PATH), exist_ok=True)
        if not os.path.exists(SUPPLY_DATA_PATH):
            with open(SUPPLY_DATA_PATH, 'w', encoding='utf-8') as f:
                json.dump([None, {}], f, ensure_ascii=False, indent=2)

        with open(SUPPLY_DATA_PATH, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            if isinstance(raw_data, list) and len(raw_data) == 2:
                existing_data = raw_data[1]
            else: 
                existing_data = {}
        
        self._last_update_time = datetime.now()
        with open(SUPPLY_DATA_PATH, 'w', encoding='utf-8') as f:
            f.write(json.dumps(
                [self._last_update_time.isoformat(), self.main_token_data], 
                indent=4
            ))
       
    async def _parse_tokens(self, ):
        
        #получаем весь набор токенов мекс + топ 2000 кмк (айди и цирк сапплай)
        token_list = []
        for search_list_name, search_list in CMC_SEARCH_LISTS.items():
            self.logger.info(f'Fetching tokens list for {search_list_name}')
            token_list += await self._search_query(1, search_list['limit'], additional_params=search_list['params'])
        
        raw_token_dict = {token['id']: token for token in token_list}
        unique_tokens = list(raw_token_dict.values())
        parsed_token_list = []
        for token in unique_tokens:
            mcap = 0
            volume = 0
            for quote in token.get('quotes',[]): 
                if quote.get("name", '') == "USD": 
                    mcap = quote.get('marketCap')
                    volume = quote.get('volume24h')
            if not (mcap and volume): 
                continue
            if not (mcap > MIN_MCAP and volume >MIN_VOLUME): 
                continue
            parsed_token_list.append( 
                {
                    'id': token.get('id'),
                    'name': token.get('name'),
                    'symbol': token.get('symbol'),
                    'circulating_supply': max(int(token.get('circulatingSupply')), int(token.get('selfReportedCirculatingSupply'))),
                    'total_supply': token.get('totalSupply'),
                }
            )

        self.logger.info(f'Parsed {len(parsed_token_list)} tokens')

        main_data_dict = {
            chain_name: {}
            for chain_name in CHAIN_NAMES
        }
        chunk_size = CACHE_UPDATE_BATCH_SIZE
        parsed_contracts = 0
        parsed_tokens = 0
        for i in range(0, len(parsed_token_list), chunk_size):
            self.logger.info(f'Processing chunk {i//chunk_size+1}/{len(parsed_token_list)//chunk_size+1}')
            chunk = parsed_token_list[i:i + chunk_size]

            ids = [token.get('id') for token in chunk]
            data = await self._get_cmc_tokens_data_by_ids(ids)
            if not data:
                continue
            decimals_tasks = []
            for token in chunk:
                id = token.get('id')
                token_data = data.get(str(id))
                if not token_data:
                    continue
                
                contract_addresses = token_data.get('contract_address', [])
                if not contract_addresses:
                    continue
                
                for contract_data in contract_addresses:
                    address = contract_data.get('contract_address','').split('#')[0]
                    if not address or address.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee": 
                        continue
                    platform = contract_data.get('platform')
                    chain_name = platform.get('name')
                    if chain_name not in list(CMC_PLATFORM_NAMES.keys()):
                        continue
                    chain_name = CMC_PLATFORM_NAMES.get(chain_name)
                    if chain_name not in CHAIN_NAMES:
                        continue
                    if chain_name == 'SOLANA':
                        decimals_tasks.append((None, None, None))
                    else: 
                        address = Web3.to_checksum_address(address)
                        if self._is_banned(address):
                            self.logger.debug(f'Skipping banned token {address}')
                            continue
                        decimals_tasks.append((self.helper_evm._get_token_decimals(address, chain_name), address, chain_name))
                    main_data_dict[chain_name][address] = {
                        'ticker': token.get('symbol', '').lower(),
                        'circulating_supply': token.get('circulating_supply'),
                        'total_supply': token.get('total_supply'),
                        'token_address': address,
                        'cmc_id': token.get('id'),
                    }
                    parsed_contracts += 1

            self.logger.info(f"{len(decimals_tasks)} decimals tasks")
            results = await asyncio.gather(*[task for task, _ , _ in decimals_tasks if task is not None])
            for result, (address, chain_name) in zip(results, [(address, chain_name) for _, address, chain_name in decimals_tasks if _ is not None]):
                if result is not None:
                    main_data_dict[chain_name][address]['decimals'] = result
                parsed_tokens += 1
            self.logger.success(f'Processed chunk {i//chunk_size+1}/{len(parsed_token_list)//chunk_size+1}')
        
        # Fetch prices in batches
        bsc_tokens = list(main_data_dict['BSC'].items())
        self.logger.info(f"Fetching prices for {len(bsc_tokens)} BSC tokens in batches of {CACHE_UPDATE_BATCH_SIZE}")
        
        for i in range(0, len(bsc_tokens), CACHE_UPDATE_BATCH_SIZE):
            batch = bsc_tokens[i:i+CACHE_UPDATE_BATCH_SIZE]
            price_tasks = [
                self.gecko.get_token_price_simple('BSC', address)
                for address, data in batch
            ]
            prices = await asyncio.gather(*price_tasks, return_exceptions=True)
            
            for (address, data), price in zip(batch, prices):
                if isinstance(price, Exception):
                    self.logger.warning(f"Failed to get price for {data['ticker']}: {price}")
                    main_data_dict['BSC'][address]['last_price'] = 0
                else:
                    main_data_dict['BSC'][address]['last_price'] = price
            
            self.logger.info(f"Updated prices for batch {i//CACHE_UPDATE_BATCH_SIZE+1}/{(len(bsc_tokens)-1)//CACHE_UPDATE_BATCH_SIZE+1}")
        
        # Обновляем данные в памяти
        self.main_token_data = main_data_dict
        self.logger.success(f'Found {parsed_contracts} contracts for {parsed_tokens} tokens')
        
        # Сохраняем данные в JSON файлы
        await self._update_token_cache_json()
        
        self.logger.success(f'Token data updated and saved successfully')
        
    async def _scheduled_parse_loop(self, update_callback:Callable=None):
        while True:
            try:
                if self._should_run_parse():
                    self.logger.info(f'Starting scheduled parse')
                    await self._parse_tokens()
                    if update_callback:
                        update_callback()
                
                await asyncio.sleep(PARSED_DATA_CHECK_DELAY_DAYS * 24 * 60 * 60)
                
            except Exception as e:
                self.logger.error(f'Error in scheduled parse loop: {str(e)}')
                self.logger.warning(f'Waiting 1 hour before retrying')
                await asyncio.sleep(60 * 60)

    async def start_scheduled_parsing_loop_task(self, update_callback:Callable=None):
        if self._parser_task is None or self._parser_task.done():
            if self._should_run_parse():
                await self._parse_tokens()
            self._parser_task = asyncio.create_task(self._scheduled_parse_loop(update_callback=update_callback))
            return True
        else:
            self.logger.warning(f'Scheduled parsing task already running')
            return False

    async def force_parse(self):
        self.logger.info(f'Force parsing requested')
        await self._parse_tokens()

    async def get_token_data(self, token_address):
        """
        Запросит токен сапплай из базы данных
        Если не найдет, запросит через API
        Если апи не даст ответ - вернет {}

        Возвращает:
            dict: Словарь с данными: {circulating_supply: int, pools: list<dict>}
        """
        
        try: 
            token_data = self.main_token_data.get(token_address)
            if token_data:
                return token_data
            else:
                self.logger.warning(f'No parsed token data for {token_address}')
                return {}
        except Exception as e:
            import traceback
            self.logger.error(f'Error getting token data for {token_address}: {str(e)}')
            self.logger.error(traceback.format_exc())
            return {}