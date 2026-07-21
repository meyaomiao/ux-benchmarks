from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/m5", tags=["M5 · Coverage Dashboard"])

_NI = lambda issue: HTTPException(status_code=501, detail=f"Not implemented — see issue #{issue}")

@router.get("/coverage")
async def get_coverage_matrix(): raise _NI(27)

@router.get("/coverage/{cell_id}/{competitor_id}")
async def get_cell_coverage(cell_id: str, competitor_id: str): raise _NI(28)

@router.post("/coverage/recompute")
async def recompute_coverage(): raise _NI(26)

@router.get("/reports")
async def list_reports(): raise _NI(30)

@router.post("/reports/generate")
async def generate_report(): raise _NI(30)
