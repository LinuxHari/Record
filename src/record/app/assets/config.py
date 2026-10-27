PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

ALLOWED_FILE_TYPES = frozenset({PDF_CONTENT_TYPE, DOCX_CONTENT_TYPE})
MAX_ASSET_SIZE_BYTES = 500 * 1024 * 1024
MIN_ASSET_NAME_LENGTH = 5
MAX_ASSET_NAME_LENGTH = 255
