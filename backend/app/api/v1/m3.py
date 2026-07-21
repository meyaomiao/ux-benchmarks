from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/m3", tags=["M3 · Collection Engine"])

_NI = lambda issue: HTTPException(status_code=501, detail=f"Not implemented — see issue #{issue}")

@router.get("/queue")
async def get_queue_status(): raise _NI(14)

@router.post("/queue/pin")
async def manual_pin(): raise _NI(14)

@router.get("/queue/{cell_id}/shortlist")
async def get_shortlist(cell_id: str): raise _NI(14)

@router.get("/source-registry")
async def list_source_registry(): raise _NI(16)

@router.delete("/source-registry/{source_id}")
async def delete_source_registry_entry(source_id: str): raise _NI(16)
