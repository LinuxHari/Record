import uuid
from datetime import datetime
from typing import Annotated, List

from fastapi import APIRouter, Depends
from pydantic import (
    AliasChoices,
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from record.aws.s3_service import MultipartPart
from record.db.sql.postgres.session import get_pg_session, get_pg_transaction
from record.handlers.response_handler import GlobalResponseHandler
from record.app.shared.dependencies import (
    AccessClaims,
    get_asset_service,
    get_current_user,
)
from record.app.assets.service import AssetService
from record.app.assets.validators import (
    asset_name_validator,
    asset_size_validator,
    asset_type_validator,
)

router = APIRouter(
    prefix="/assets",
    tags=["Assets"],
    route_class=GlobalResponseHandler,
    dependencies=[Depends(get_current_user)],
)


AssetName = Annotated[
    str,
    Field(
        title="File name",
        description="Name of the file going to be uploaded",
        min_length=asset_name_validator.min_len,
        max_length=asset_name_validator.max_len,
    ),
    AfterValidator(asset_name_validator.validate),
]

AssetType = Annotated[
    str,
    Field(
        title="File type",
        description="MIME type of the file (PDF or DOCX)",
        min_length=asset_type_validator.min_len,
        max_length=asset_type_validator.max_len,
    ),
    AfterValidator(asset_type_validator.validate),
]

AssetSize = Annotated[
    int,
    Field(
        title="File size",
        description="Size of the file in bytes",
        gt=asset_size_validator.min_value - 1,
        le=asset_size_validator.max_value,
    ),
    AfterValidator(asset_size_validator.validate),
]


class AssetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: AssetName
    type: AssetType
    size: AssetSize


class AssetUploadResponse(BaseModel):
    part_number: int
    url: str


class AssetPartPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    etag: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1024)
    ] = Field(validation_alias=AliasChoices("ETag", "etag"))
    part_number: int = Field(
        strict=True,
        ge=1,
        le=AssetService.MAX_MULTIPART_PARTS,
        validation_alias=AliasChoices(
            "PartNumber", "part_number", "partNumber", "partnumber"
        ),
    )


class AssetCompletePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: List[AssetPartPayload] = Field(
        min_length=1, max_length=AssetService.MAX_MULTIPART_PARTS
    )


class AssetListResponse(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    type: str
    size: int
    uploaded_at: datetime
    updated_at: datetime


@router.post("/", dependencies=[Depends(get_pg_session)])
async def upload_asset(
    payload: AssetPayload,
    asset_service: AssetService = Depends(get_asset_service),
    user: AccessClaims = Depends(get_current_user),
) -> List[AssetUploadResponse]:
    result = await asset_service.initiate_asset_upload(
        user_id=user["sub"], asset_metadata=payload.model_dump()
    )
    return result


@router.get("/", dependencies=[Depends(get_pg_session)])
async def list_assets(
    asset_service: AssetService = Depends(get_asset_service),
    user: AccessClaims = Depends(get_current_user),
) -> List[AssetListResponse]:
    result = await asset_service.list_assets(user_id=user["sub"])
    return result


# @router.put("/{asset_id}")
# def update_asset(asset_id: int):
#     return {"message": f"Asset {asset_id} updated successfully"}

# @router.delete("/{asset_id}")
# def delete_asset(asset_id: int):
#     return {"message": f"Asset {asset_id} deleted successfully"}


@router.post("/{upload_id}/complete", dependencies=[Depends(get_pg_transaction)])
async def upload_asset_complete(
    upload_id: str,
    payload: AssetCompletePayload,
    asset_service: AssetService = Depends(get_asset_service),
    user: AccessClaims = Depends(get_current_user),
) -> None:
    parts: list[MultipartPart] = [
        {"ETag": part.etag, "PartNumber": part.part_number}
        for part in payload.parts
    ]
    await asset_service.asset_upload_complete(
        user_id=user["sub"], upload_id=upload_id, parts=parts
    )
