from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List

from record.handlers.response_handler import GlobalResponseHandler
from record.app.shared.dependencies import AccessClaims, get_asset_service, get_current_user
from record.app.assets.service import AssetService

router = APIRouter(
    prefix="/assets",
    tags=["Assets"],
    route_class=GlobalResponseHandler,
    dependencies=[Depends(get_current_user)]
)

class AssetUploadResponse(BaseModel):
    part_number: int
    url: str

@router.post("/")
async def upload_asset(asset_service: AssetService = Depends(get_asset_service)) -> List[AssetUploadResponse]:
    result = await asset_service.initiate_asset_upload() 
    return result

@router.get("/")
async def list_assets(asset_service: AssetService = Depends(get_asset_service), user: AccessClaims = Depends(get_current_user)):
    result = await asset_service.list_assets(user_id=user["sub"])
    return result

# @router.put("/{asset_id}")
# def update_asset(asset_id: int):
#     return {"message": f"Asset {asset_id} updated successfully"}

# @router.delete("/{asset_id}")
# def delete_asset(asset_id: int):
#     return {"message": f"Asset {asset_id} deleted successfully"}

@router.post("/{asset_id}/complete")
def upload_asset_complete(asset_id: int):
    return {"message": f"Asset {asset_id} completed successfully"}