from io import BytesIO
from typing import AsyncGenerator
from dataclasses import dataclass

from docling.service_client import AsyncDoclingServiceClient
from docling.chunking import HybridChunker
from docling.datamodel.service.options import ConvertDocumentsOptions
from docling.datamodel.document import DocumentStream
from docling.datamodel.base_models import OutputFormat

from transformers import AutoTokenizer

from record.dependencies import get_settings


@dataclass
class ParsedContentPayload:
    text: str
    pages: list[int]


class ChunkService:
    def __init__(self):
        settings = get_settings()
        self.docling_server_url = settings.docling_server_url
        self.tokenizer = AutoTokenizer.from_pretrained(settings.embedding_model)
        self.chunker = HybridChunker(
            tokenizer=self.tokenizer,
            max_tokens=settings.chunk_max_tokens,
            merge_peers=True,
        )

    async def parse_content(
        self, *, source_stream: BytesIO, file_name: str
    ) -> AsyncGenerator[ParsedContentPayload, None]:
        async with AsyncDoclingServiceClient(url=self.docling_server_url) as converter:
            source_stream.seek(0)

        doc_stream = DocumentStream(name=file_name, stream=source_stream)

        job = await converter.submit(
            source=doc_stream,
            options=ConvertDocumentsOptions(to_formats=[OutputFormat.MARKDOWN])
        )

        result = await job.result()

        for chunk in self.chunker.chunk(dl_doc=result.document):
            pages = sorted(
                set(
                    prov.page_no
                    for item in chunk.meta.doc_items
                    for prov in item.prov
                    if hasattr(prov, "page_no")
                )
            )

            yield ParsedContentPayload(
                text=self.chunker.contextualize(chunk), pages=pages
            )
