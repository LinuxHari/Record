from io import BytesIO
from typing import AsyncGenerator
from langchain_ollama import OllamaEmbeddings

from record.aws.s3_service import AwsS3
from record.app.ai.embedding.models import Embeddings
from record.app.ai.embedding.chunk_service import ChunkService, ParsedContentPayload
from record.app.ai.embedding.repository import EmbeddingRepository
from record.dependencies import get_settings


class EmbeddingService:
    def __init__(
        self,
        *,
        chunk_service: ChunkService,
        s3_service: AwsS3,
        embedding_repository: EmbeddingRepository,
    ):
        self.chunk_service = chunk_service
        self.s3_Service = s3_service
        self.embedding_repository = embedding_repository
        self.embedding_model = get_settings().embedding_model

    async def file_parser(
        self, *, s3_key: str
    ) -> AsyncGenerator[ParsedContentPayload, None]:
        async for file_stream in self.s3_Service.stream_s3_object(key=s3_key):
            async for chunk in self.chunk_service.parse_content(
                source_stream=BytesIO(file_stream),
                file_name=s3_key
            ):
                yield chunk

    async def embed(self, content: str) -> list[float]:
        embeddings = OllamaEmbeddings(
            model=self.embedding_model,
            dimensions=1024,
        )

        return await embeddings.aembed_query(content)

    async def embed_asset(self, *, s3_key: str, user_id: str, asset_id: str) -> None:
        async for chunk in self.file_parser(s3_key=s3_key):
            embeddings = await self.embed(chunk.text)

            await self.embedding_repository.create(
                Embeddings(
                    user_id=user_id,
                    asset_id=asset_id,
                    text_context=chunk.text,
                    embeddings=embeddings,
                    pages=chunk.pages,
                )
            )
