from record.app.assets.config import (
    ALLOWED_FILE_TYPES,
    MAX_ASSET_NAME_LENGTH,
    MAX_ASSET_SIZE_BYTES,
    MIN_ASSET_NAME_LENGTH,
)
from record.app.shared.validators import IntegerValidator, StringValidator


class AssetNameValidator(StringValidator):
    label = "File name"


class AssetTypeValidator(StringValidator):
    label = "File type"

    def _validate_rules(self, value: str) -> None:
        if value not in ALLOWED_FILE_TYPES:
            raise ValueError("File type must be PDF or DOCX")


asset_name_validator = AssetNameValidator(
    min_len=MIN_ASSET_NAME_LENGTH,
    max_len=MAX_ASSET_NAME_LENGTH,
)
asset_type_validator = AssetTypeValidator(
    min_len=min(map(len, ALLOWED_FILE_TYPES)),
    max_len=max(map(len, ALLOWED_FILE_TYPES)),
)
asset_size_validator = IntegerValidator(
    min_value=1,
    max_value=MAX_ASSET_SIZE_BYTES,
)
