import asyncio
from core import Runner 
from config import DEFAULT_LOGS_FILE, LOGS_SIZE, SOFT_NAME
import warnings
import sys
from loguru import logger
from asyncio import WindowsSelectorEventLoopPolicy
asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
warnings.filterwarnings("ignore", message="Curlm alread closed")

logger.remove()
logger.add(
    sys.stdout,
    format=f"<green>{{time:HH:mm:ss}}</green> | [{SOFT_NAME}] | <level>{{level: <8}}</level> | <level>{{message}}</level>",
    colorize=True
)
logger.add(DEFAULT_LOGS_FILE, rotation=LOGS_SIZE)

async def main(): 
    runner = Runner() 
    await runner.start()

if __name__ == '__main__':
    asyncio.run(main())