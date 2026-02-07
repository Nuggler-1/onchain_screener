from curl_cffi.requests import AsyncSession, Response
from curl_cffi.requests.errors import RequestsError
import asyncio
from typing import Optional, Any
from config import REQUEST_RETRY, REQUEST_TIMEOUT, ERROR_429_RETRIES, ERROR_429_DELAY
from .logger_utils import get_logger

class HttpClient:
    def __init__(
        self,
        base_url: str = "",
        headers: Optional[dict] = None,
        timeout: int = REQUEST_TIMEOUT,
    ):
        self.base_url = base_url
        self.headers = headers or {}
        self.timeout = timeout
        self.logger = get_logger("HTTP")
        self._session: Optional[AsyncSession] = None

    async def _get_session(self) -> AsyncSession:
        if self._session is None:
            self._session = AsyncSession()
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        url: str,
        retries: int = REQUEST_RETRY,
        **kwargs,
    ) -> Response:
        full_url = self.base_url + url if not url.startswith("http") else url
        merged_headers = {**self.headers, **kwargs.pop("headers", {})}
        
        rate_limit_attempts = 0
        attempt = 0
        
        while True:
            try:
                session = await self._get_session()
                response = await session.request(
                    method=method,
                    url=full_url,
                    headers=merged_headers,
                    timeout=self.timeout,
                    **kwargs,
                )
                
                if response.status_code == 429:
                    rate_limit_attempts += 1
                    if rate_limit_attempts > ERROR_429_RETRIES:
                        self.logger.error(f"Rate limit exceeded after {ERROR_429_RETRIES} retries: {full_url}")
                        return response
                    self.logger.warning(f"Rate limited (429), waiting {ERROR_429_DELAY}s... (attempt {rate_limit_attempts}/{ERROR_429_RETRIES})")
                    await asyncio.sleep(ERROR_429_DELAY)
                    continue
                
                return response
                
            except (RequestsError, asyncio.TimeoutError, TimeoutError) as e:
                attempt += 1
                if attempt > retries:
                    self.logger.error(f"Request failed after {retries} retries: {full_url} - {e}")
                    return None
                self.logger.warning(f"Request error, retrying ({attempt}/{retries}): {e}")
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Unexpected error: {full_url} - {str(e)}")
                return None
                

    async def get(self, url: str, **kwargs) -> Response:
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> Response:
        return await self._request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> Response:
        return await self._request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> Response:
        return await self._request("DELETE", url, **kwargs)

    async def get_json(self, url: str, **kwargs) -> Any:
        response = await self.get(url, **kwargs)
        return {} if not response else response.json()

    async def post_json(self, url: str, **kwargs) -> Any:
        response = await self.post(url, **kwargs)
        return {} if not response else response.json()
