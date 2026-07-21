from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/m4", tags=["M4 · Asset Review & Annotation"])

_NI = lambda issue: HTTPException(status_code=501, detail=f"Not implemented — see issue #{issue}")

@router.get("/assets")
async def list_assets(): raise _NI(22)

@router.post("/assets/accept", status_code=201)
async def accept_asset(): raise _NI(23)

@router.delete("/assets/{asset_id}")
async def reject_asset(asset_id: str): raise _NI(22)

@router.get("/observations")
async def list_observations(): raise _NI(24)

@router.post("/observations", status_code=201)
async def create_observation(): raise _NI(24)

@router.get("/observations/{observation_id}")
async def get_observation(observation_id: str): raise _NI(24)

@router.post("/observations/{observation_id}/claims", status_code=201)
async def add_claim(observation_id: str): raise _NI(25)
