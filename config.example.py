SOFT_NAME = "Onchain Screener"

#============================= SOFT ALERT CONFIG ===================================

EVENT_TRADE_DIRECTION = {
    'transfer': 'short',
    'mint': 'short',
    'burn': 'long'
}

FILTER_CONFIG = {
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

ALERT_TG_BOT_TOKEN = ''
TECH_ALERTS_CHAT_ID = ''
USER_ALERTS_CHAT_ID = ''

MANAGER_TG_BOT_TOKEN = ''
MANAGER_TG_BOT_IDS = [
    '',
    #''
]

#============================= ONCHAIN SETTIGNS ===================================

RPC = {
    "ARBITRUM": 'https://rpc.ankr.com/arbitrum/',
    "ETHEREUM": 'https://eth-mainnet.g.alchemy.com/v2/',
    "BSC": 'https://lb.drpc.live/bsc/', 
    "BASE": 'https://lb.drpc.live/base/',
    "SOLANA": 'https://mainnet.helius-rpc.com/?api-key=',
}


WS_RPC = {
    "ARBITRUM": 'wss://lb.drpc.live/arbitrum/',
    "ETHEREUM": 'wss://lb.drpc.live/ethereum/',
    "BASE": 'wss://lb.drpc.live/base/',
    "BSC": 'wss://lb.drpc.live/bsc/',
    "SOLANA": '',#соль без поддержки вебсокета пока
}

EVENT_SIGNATURES = [
    '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef' #трансфер
]

#имена чейнов для софта
CHAIN_NAMES = {
    'ETHEREUM',
    'ARBITRUM',
    'BSC',
    'BASE',
    'SOLANA'
}


#============================= NETWORK SETTINGS ===================================


#------WS SETTINGS
SIGNAL_WS_URL = "ws://localhost:8765"
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
    "base top 300": {
        "params": 'platformId=199',
        "limit": 300
    },
    "bsc top 500": {
        "params": 'platformId=1839',
        "limit": 300
    },
    "arbitrum top 200": {
        "params": 'platformId=11841',
        "limit": 200
    },
    "eth top 500": {
        "params": 'platformId=1027',
        "limit": 500
    }
}

#------GECKO DATA

GECKO_API_KEY = ''
GECKO_CHAIN_NAMES = {
    'ETHEREUM': 'eth',
    'SOLANA': 'solana',
    'BSC': 'bsc',
    'ARBITRUM': 'arbitrum',
    'BASE': 'base'
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