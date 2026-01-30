DEXSCREENER_BASE_URL = "https://dexscreener.com"    
SCAN_URL = {
    "ETHEREUM": "https://etherscan.io/tx/",
    "ARBITRUM": "https://arbiscan.io/tx/",
    "BSC": "https://bscscan.com/tx/",
    "SOLANA": "https://solscan.io/tx/",
    "BASE": "https://basescan.org/tx/"
}
ARKHAM_URL = "https://intel.arkm.com/explorer/"
MEXC_URL = "https://www.mexc.com/futures/"
BYBIT_URL = "https://www.bybit.com/trade/usdt/"
BITGET_URL = "https://www.bitget.com/ru/futures/usdt/"
GATE_URL = "https://www.gate.com/ru/futures/USDT/"
BINANCE_URL = "https://www.binance.com/ru/futures/"
OKX_URL = "https://www.okx.com/ru/trade-swap/"
KUCOIN_URL = "https://www.kucoin.com/trade/futures/"

def futures_link_map(exchange_slug:str, ticker:str): 
    link_map = {
        'mexc': MEXC_URL+ticker.upper()+"_USDT",
        'bybit': BYBIT_URL+ticker.upper()+"USDT",
        'bitget': BITGET_URL+ticker.upper()+"USDT",
        'gate': GATE_URL+ticker.upper()+"_USDT",
        'binance': BINANCE_URL+ticker.upper()+"USDT",
        'okx': OKX_URL+ticker.upper()+"-USDT-SWAP",
        'kucoin': KUCOIN_URL+ticker.upper()+"USDTM"
    }
    emoji_map = {
        'mexc': '🔵',
        'bybit': '🟠',
        'bitget': '🟢',
        'gate': '⚪',
        'binance': '🟡',
        'okx': '⚫',
        'kucoin': '🟤'

    }
    return link_map.get(exchange_slug, ''), emoji_map.get(exchange_slug, '')

OKX_DEX_URL = "https://web3.okx.com/ru/token/"
