from fastapi import APIRouter, Depends

from record.handlers.response_handler import GlobalResponseHandler
from record.app.shared.dependencies import get_asset_service
from record.app.assets.service import AssetService

router = APIRouter(
    prefix="/assets",
    tags=["Assets"],
    route_class=GlobalResponseHandler,
    dependencies=[Depends(get_asset_service)]
)

@router.post("/")
async def upload_asset(asset_service: AssetService):
    result = await asset_service.initiate_asset_upload() 
    return result

@router.get("/")
def list_assets():
    return {"message": "List of assets"}

# @router.put("/{asset_id}")
# def update_asset(asset_id: int):
#     return {"message": f"Asset {asset_id} updated successfully"}

# @router.delete("/{asset_id}")
# def delete_asset(asset_id: int):
#     return {"message": f"Asset {asset_id} deleted successfully"}

@router.post("/{asset_id}/complete")
def upload_asset_complete(asset_id: int):
    return {"message": f"Asset {asset_id} completed successfully"}