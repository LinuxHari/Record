import redis.asyncio as aioredis
from redis.asyncio.retry import Retry
from redis.exceptions import RedisError

class RedisService:
    TIMEOUT = 5.0
    SOCKET_TIMEOUT = 5.0

    def __init__(self, *, name: str, url: str, max_connections: int) -> None:
        self.name:str = name
        self.url:str = url
        self._pool: aioredis.BlockingConnectionPool | None = None
        self.max_connections:int = max_connections

    async def connect(self) -> None:
        if self._pool is not None:
            return
        
        retry_strategy = Retry(backoff=1, retries=3)
        
        self._pool = aioredis.BlockingConnectionPool.from_url(
            self.url,
            max_connections= self.max_connections,
            timeout=self.TIMEOUT,
            socket_timeout=self.SOCKET_TIMEOUT,
            retry=retry_strategy,
            retry_on_timeout=True,
            decode_responses=True
        )

    def _get_client(self) -> aioredis.Redis:
        if self._pool is None:
            raise RuntimeError(f"Redis service {self.name} is not initialized. Call connect() first.")

        return aioredis.Redis(connection_pool=self._pool)

    async def get(self, key: str) -> str | None:
        try:
            async with self._get_client() as client:
                return await client.get(key)
        except RedisError as e:
            print(f"Redis get error: {str(e)}")
            return None 

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        try:
            async with self._get_client() as client:
                return await client.setex(key, seconds, value)
        except RedisError as e:
            print(f"Redis setex error: {str(e)}")
            return False

    async def disconnect(self):
        if self._pool:
            await self._pool.aclose()
            self._pool = None