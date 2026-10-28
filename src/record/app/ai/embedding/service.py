import logging

from langchain_ollama import OllamaEmbeddings

from record.aws.s3_service import AwsS3
from record.app.ai.embedding.models import Embeddings
from record.app.ai.embedding.chunk_service import ChunkService
from record.app.ai.embedding.hash_service import HashService
from record.app.ai.embedding.repository import EmbeddingRepository
from record.dependencies import get_settings

from record.app.assets.models import AssetStatus
from record.app.assets.repository import AssetRepository

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(
        self,
        *,
        chunk_service: ChunkService,
        s3_service: AwsS3,
        hash_service: HashService,
        embedding_repository: EmbeddingRepository,
        asset_repository: AssetRepository,
    ):
        self.chunk_service = chunk_service
        self.s3_Service = s3_service
        self.hash_service = hash_service
        self.embedding_repository = embedding_repository
        self.asset_repository = asset_repository
        self.embedding_model = get_settings().embedding_model

    async def embed(self, content: str) -> list[float]:
        embeddings = OllamaEmbeddings(
            model=self.embedding_model,
            dimensions=1024,
        )

        return await embeddings.aembed_query(content)

    async def embed_asset(self, *, s3_key: str, user_id: str, asset_id: str) -> None:
        try:
            presigned_url = await self.s3_Service.generate_presigned_get_url(
                key=s3_key, expires_in=24 * 60 * 60
            )
            async for chunk in self.chunk_service.parse_content(
                source=presigned_url,
            ):

                embeddings = await self.embed(chunk.text)
                headings = [str(heading).strip() for heading in chunk.meta.headings]
                context_hash = self.hash_service.hash(chunk.text)
                section = " / ".join(headings) if len(headings) > 0 else "/"
                section_hash = self.hash_service.hash(section)

                chunk_primary_loc = chunk.doc_items[0].self_ref

                await self.embedding_repository.create(
                    data=Embeddings(
                        user_id=user_id,
                        asset_id=asset_id,
                        text_context=chunk.text,
                        context_hash=context_hash,
                        embeddings=embeddings,
                        section=section,
                        section_hash=section_hash,
                        location=chunk_primary_loc,
                    )
                )

            await self.asset_repository.update_by_id(
                user_id=user_id,
                asset_id=asset_id,
                update_data={"status": AssetStatus.SUCCESS},
            )

        except Exception as exc:
            logger.error(
                f"Error while embedding asset {asset_id} from key {s3_key}",
                extra={"exception_type": type(exc).__name__},
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            await self.asset_repository.update_by_id(
                user_id=user_id,
                asset_id=asset_id,
                update_data={"status": AssetStatus.FAILED},
            )
