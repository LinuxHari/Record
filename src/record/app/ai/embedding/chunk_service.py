from typing import AsyncGenerator
from dataclasses import dataclass

from docling.service_client import AsyncDoclingServiceClient
from docling.chunking import HierarchicalChunker
from docling.datamodel.service.options import ConvertDocumentsOptions
from docling.datamodel.base_models import OutputFormat

from record.dependencies import get_settings

@dataclass
class DocItem:
    self_ref: str

@dataclass
class ParsedContentPayload:
    text: str
    headings: list[str]
    doc_items: list[DocItem]


class ChunkService:
    def __init__(self):
        settings = get_settings()
        self.docling_server_url = settings.docling_server_url
        self.chunker = HierarchicalChunker(
            always_emit_headings=True
        )

    async def parse_content(
        self, *, source: str
    ) -> AsyncGenerator[ParsedContentPayload, None]:
        async with AsyncDoclingServiceClient(url=self.docling_server_url) as converter:

            job = await converter.submit(
            source=source,
            options=ConvertDocumentsOptions(to_formats=[OutputFormat.JSON])
            )

            result = await job.result()

            for chunk in self.chunker.chunk(dl_doc=result.document):
                yield ParsedContentPayload(
                    text=chunk.text,
                    headings=chunk.meta.headings,
                    doc_items = chunk.meta.doc_items
                )

            del result.document
            del result
