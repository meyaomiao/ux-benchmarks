from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/m2", tags=["M2 · Mapping Cards"])

_NI = lambda issue: HTTPException(status_code=501, detail=f"Not implemented — see issue #{issue}")

@router.get("/mapping-cards")
async def list_mapping_cards(): raise _NI(11)

@router.post("/mapping-cards", status_code=201)
async def create_mapping_card(): raise _NI(11)

@router.get("/mapping-cards/{cell_id}")
async def get_mapping_card(cell_id: str): raise _NI(11)

@router.patch("/mapping-cards/{cell_id}")
async def update_mapping_card(cell_id: str): raise _NI(11)
