from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/m1", tags=["M1 · Grid Management"])

_NI = lambda issue: HTTPException(status_code=501, detail=f"Not implemented — see issue #{issue}")

@router.get("/cells")
async def list_cells(): raise _NI(8)

@router.post("/cells", status_code=201)
async def create_cell(): raise _NI(8)

@router.get("/cells/{cell_id}")
async def get_cell(cell_id: str): raise _NI(8)

@router.patch("/cells/{cell_id}")
async def update_cell(cell_id: str): raise _NI(8)

@router.get("/cells/{cell_id}/changelog")
async def get_cell_changelog(cell_id: str): raise _NI(8)

@router.get("/inbox")
async def list_unmapped_inbox(): raise _NI(10)

@router.post("/inbox/{inbox_id}/resolve")
async def resolve_inbox_item(inbox_id: str): raise _NI(10)
