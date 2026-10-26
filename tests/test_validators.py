import pytest
from pydantic import ValidationError

from record.app.assets.config import (
    ALLOWED_FILE_TYPES,
    DOCX_CONTENT_TYPE,
    MAX_ASSET_SIZE_BYTES,
    PDF_CONTENT_TYPE,
)
from record.app.assets.router import AssetCompletePayload, AssetPayload
from record.app.shared.validators import IntegerValidator, StringValidator
from record.app.user.validators import password_validator


@pytest.mark.parametrize("file_type", [PDF_CONTENT_TYPE, DOCX_CONTENT_TYPE])
def test_asset_payload_accepts_supported_file_types(file_type: str) -> None:
    payload = AssetPayload(name="report.pdf", type=file_type, size=1)

    assert payload.type == file_type


def test_asset_payload_rejects_unsupported_file_types() -> None:
    with pytest.raises(ValidationError):
        AssetPayload(name="report.txt", type="text/plain", size=1)


def test_asset_complete_payload_accepts_s3_part_metadata() -> None:
    payload = AssetCompletePayload(
        parts=[
            {"ETag": '"etag-1"', "PartNumber": 1},
            {"etag": '"etag-2"', "partnumber": 2},
        ]
    )

    assert [part.part_number for part in payload.parts] == [1, 2]


def test_asset_complete_payload_rejects_more_than_nine_parts() -> None:
    parts = [
        {"ETag": f'"etag-{part_number}"', "PartNumber": part_number}
        for part_number in range(1, 11)
    ]

    with pytest.raises(ValidationError):
        AssetCompletePayload(parts=parts)


@pytest.mark.parametrize(
    "parts",
    [
        [],
        [{"ETag": "", "PartNumber": 1}],
        [{"ETag": '"etag"', "PartNumber": 0}],
        [{"ETag": '"etag"', "PartNumber": 10}],
        [{"ETag": '"etag"', "PartNumber": 1, "unexpected": True}],
    ],
)
def test_asset_complete_payload_rejects_invalid_part_metadata(
    parts: list[dict[str, object]],
) -> None:
    with pytest.raises(ValidationError):
        AssetCompletePayload(parts=parts)


def test_asset_payload_enforces_asset_name_and_size_limits() -> None:
    valid_payload = {
        "name": "a" * 255,
        "type": PDF_CONTENT_TYPE,
        "size": MAX_ASSET_SIZE_BYTES,
    }

    assert AssetPayload(**valid_payload).size == MAX_ASSET_SIZE_BYTES

    with pytest.raises(ValidationError):
        AssetPayload(name="tiny", type=PDF_CONTENT_TYPE, size=1)
    with pytest.raises(ValidationError):
        AssetPayload(name="report.pdf", type=PDF_CONTENT_TYPE, size=0)
    with pytest.raises(ValidationError):
        AssetPayload(
            name="report.pdf",
            type=PDF_CONTENT_TYPE,
            size=MAX_ASSET_SIZE_BYTES + 1,
        )


def test_shared_validators_and_user_password_validator() -> None:
    string_validator = StringValidator(min_len=2, max_len=4)
    integer_validator = IntegerValidator(min_value=1, max_value=3)

    assert string_validator.validate("ok") == "ok"
    assert integer_validator.validate(2) == 2
    assert password_validator.validate("StrongPass1!") == "StrongPass1!"

    with pytest.raises(ValueError):
        integer_validator.validate(True)


def test_allowed_file_types_are_pdf_and_docx_mime_types() -> None:
    assert ALLOWED_FILE_TYPES == {PDF_CONTENT_TYPE, DOCX_CONTENT_TYPE}
