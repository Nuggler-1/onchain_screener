SOFT_NAME = "Onchain Screener"

#============================= SOFT ALERT CONFIG ===================================

EVENT_TRADE_DIRECTION = {
    'transfer': 'short',
    'mint': 'short',
    'burn': 'long',
    'claim': 'short',
    'hidden_binance_alpha': 'short',
    'usd_based_transfer': 'short',
}

FILTER_CONFIG = {
    'hidden_binance_alpha': [
        {
            "enabled": True, 
            "min_usd_size": 600_000,
            "max_usd_size": float("inf"),
            "message_tier": "🔶 Binance Alpha ",
            "auto_open": True
        }
    ],
    'usd_based_transfer': [
        {
            "enabled": True, 
            "min_usd_size": 500_000,
            "max_usd_size": 1_000_000,
            "message_tier": "💵 MID deposit ",
            "auto_open": False,
            "price_check_delay_minutes": 5,
            "price_drop_threshold_percent": 2
        },
        {
            "enabled": True, 
            "min_usd_size": 1_000_001,
            "max_usd_size": 3_000_000,
            "message_tier": "💰 BIG deposit ",
            "auto_open": False,
            "price_check_delay_minutes": 5,
            "price_drop_threshold_percent": 2
        },
        {
            "enabled": True, 
            "min_usd_size": 3_000_001,
            "max_usd_size": float("inf"),
            "message_tier": "🤑 EXTREME deposit ",
            "auto_open": False,
            "price_check_delay_minutes": 5,
            "price_drop_threshold_percent": 2
        },
    ],
    'transfer': [
        {
            "enabled": True, 
            "min_supply_percent": 0.1,
            "max_supply_percent": 0.15,
            "message_tier": "🟢 low ",
            "auto_open": False
        },
        {
            "enabled": True,
            "min_supply_percent": 0.15,
            "max_supply_percent": 0.3,
            "message_tier": "🟡 medium",
            "auto_open": False
        },
        {   
            "enabled": True,
            "min_supply_percent": 0.3,
            "max_supply_percent": 0.5,
            "message_tier": "🔴 high",
            "auto_open": False
        },
        {   
            "enabled": True, 
            "min_supply_percent": 0.5,
            "max_supply_percent": float("inf"),
            "message_tier": "🚨 extreme",
            "auto_open": True
        }
    ] ,
    'mint': [
        {
            "enabled": True, 
            "min_supply_percent": 0.1,
            "max_supply_percent": 0.15,
            "message_tier": "🟢 low ",
            "auto_open": False
        },
        {
            "enabled": True,
            "min_supply_percent": 0.15,
            "max_supply_percent": 0.3,
            "message_tier": "🟡 medium",
            "auto_open": False
        },
        {
            "enabled": True,
            "min_supply_percent": 0.3,
            "max_supply_percent": 0.5,
            "message_tier": "🔴 high ",
            "auto_open": False
        },
        {
            "enabled": True,
            "min_supply_percent": 0.5,
            "max_supply_percent": float("inf"),
            "message_tier": "🚨 extreme",
            "auto_open": True
        }
    ],
    'burn': [
        {
            "enabled": True, 
            "min_supply_percent": 0.05,
            "max_supply_percent": 0.1,
            "message_tier": "🟢 low ",
            "auto_open": False
        },
        {
            "enabled": True,
            "min_supply_percent": 0.1,
            "max_supply_percent": 0.15,
            "message_tier": "🟡 medium ",
            "auto_open": False
        },
        {
            "enabled": True,
            "min_supply_percent": 0.15,
            "max_supply_percent": 0.2,
            "message_tier": "🔴 high ",
            "auto_open": False
        },
        {
            "enabled": True,
            "min_supply_percent": 0.2,
            "max_supply_percent": float("inf"),
            "message_tier": "🚨 extreme",
            "auto_open": True
        }
    ] 
}

#============================= TG BOTS SETTINGS ===================================

ALERT_TG_BOT_TOKEN = '8441606860:'
TECH_ALERTS_CHAT_ID = '341122695'
USER_ALERTS_CHAT_ID = '-1003636568887'

MANAGER_TG_BOT_TOKEN = '8441606860:'
MANAGER_TG_BOT_IDS = [
    '341122695',
    '6393736698'
]

#============================= ONCHAIN SETTIGNS ===================================

RPC = {
    "ARBITRUM": 'https://rpc.ankr.com/arbitrum/',
    "ETHEREUM": 'https://eth-mainnet.g.alchemy.com/v2/',
    "BSC": 'https://lb.drpc.live/bsc/', 
    "BASE": 'https://lb.drpc.live/base/',
    "SOLANA": 'https://mainnet.helius-rpc.com/?api-key=----',
}


WS_RPC = {
    "ARBITRUM": 'wss://lb.drpc.live/arbitrum/',
    "ETHEREUM": 'wss://lb.drpc.live/ethereum/',
    "BASE": 'wss://lb.drpc.live/base/',
    "BSC": 'wss://lb.drpc.live/bsc/',
    "SOLANA": '',#соль без поддержки вебсокета пока
}


BINANCE_ALPHA_WALLETS = [
    #"0x55469e9db22b64dc3e058a1182df8c43d2887c6c"
    "0x73d8bd54f7cf5fab43fe4ef40a62d390644946db", #1
    "0xb5893a55965a4a01c239f852d93ac47942415231" #2
]

EVENT_SIGNATURES = [
    '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef' #трансфер
]

#имена чейнов для софта
CHAIN_NAMES = {
    'ETHEREUM',
    'ARBITRUM',
    'BSC',
    'BASE',
    #'SOLANA'
}


#============================= NETWORK SETTINGS ===================================


#------WS SETTINGS
SIGNAL_WS_URL = "ws://:8000/ws_in"
RECONNECT_ATTEMPTS = 10
RECONNECT_DELAY = 5

#------REST API SETTINGS

CACHE_UPDATE_BATCH_SIZE = 100  #количество распаралелленых запросов в пачке при обновлении ончейн-данных
DELAY_BETWEEN_BATCHES = 10 #Задержка между пачками токенов, (на платной по идее можно в ноль поставить)
REQUEST_RETRY = 3 #общее количество попыток для обычных ошибок
REQUEST_TIMEOUT = 30 #таймаут запроса в секундах
ERROR_429_RETRIES = 3 #попытки  при рейтлимите
ERROR_429_DELAY = 60 #задеркжи при рейтлимите 


#============================= PARSER SETTINGS ====================================

MIN_MCAP = 1_000_000
MIN_VOLUME = 100_000

MIN_PARSED_PRICE_SIZE_TO_CHECK = 200_000

PARSED_DATA_CHECK_DELAY_DAYS = 1 #раз в сколько дней обновлять данные 
FORCE_UPDATE_ON_START = False #обновить данные пулов для евм/соланы на запуске 

#------CMC DATA

CMC_PLATFORM_NAMES= {
    'BNB Smart Chain (BEP20)': 'BSC',
    'Arbitrum': 'ARBITRUM',
    'Ethereum': 'ETHEREUM',
    'Solana': 'SOLANA',
    'Base': 'BASE',
}
CMC_API_KEY = ''

CMC_SEARCH_LISTS = {
    "mexc": {
        "params": 'exchangeIds=544',
        "limit": 2500
    },
    "binance": {
        "params": 'exchangeIds=270',
        "limit": 700
    },
}
#------GECKO DATA

GECKO_API_KEY = ''
GECKO_CHAIN_NAMES = {
    'ETHEREUM': 'ethereum',
    'SOLANA': 'solana',
    'BSC': 'binance-smart-chain',
    'ARBITRUM': 'arbitrum-one',
    'BASE': 'base'
}

SUPPORTED_CEX_SLUGS = [
    'binance',
    'bybit',
    'kucoin',
    'okx',
    'bitget',
    'gate',
    'mexc'
]

CMC_SEARCH_LISTS = {
    "mexc": {
        "params": 'exchangeIds=544',
        "limit": 2500
    },
    "binance": {
        "params": 'exchangeIds=270',
        "limit": 700
    },
}
CMC_BLACK_LISTS = {
    "stables": {
        "params": 'tagSlugs=stablecoin',
        "limit": 700
    }, 
    "stocks": {
        "params": 'tagSlugs=tokenized-stock',
        "limit": 700
    }
}
#=============================FILE PATHS========================================

TOKEN_DATA_BASE_PATH = 'database/'

CUSTOM_RULES_PATH = TOKEN_DATA_BASE_PATH + 'custom_rules.json'

BANNED_PATH = TOKEN_DATA_BASE_PATH + 'banned.json'
SUPPLY_DATA_PATH = TOKEN_DATA_BASE_PATH + 'token_data.json'
LAST_CHECK_PATH = TOKEN_DATA_BASE_PATH + 'last_check.txt'

TP_CACHE_PATH = TOKEN_DATA_BASE_PATH + '/TP_data/'

DEFAULT_LOGS_FILE = 'logs.txt'
LOGS_SIZE = '10 MB'
