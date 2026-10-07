from fastapi import APIRouter

router = APIRouter("/assets", tags=["Assets"])

@router.post("/")
def upload_asset():
    return {"message": "Asset uploaded successfully"}

@router.get("/")
def list_assets():
    return {"message": "List of assets"}

@router.put("/{asset_id}")
def update_asset(asset_id: int):
    return {"message": f"Asset {asset_id} updated successfully"}