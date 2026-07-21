from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/m0", tags=["M0 · Competitor Registry"])

_NI = lambda issue: HTTPException(status_code=501, detail=f"Not implemented — see issue #{issue}")

@router.get("/competitors")
async def list_competitors(): raise _NI(5)

@router.post("/competitors", status_code=201)
async def create_competitor(): raise _NI(5)

@router.get("/competitors/{competitor_id}")
async def get_competitor(competitor_id: str): raise _NI(5)

@router.patch("/competitors/{competitor_id}")
async def update_competitor(competitor_id: str): raise _NI(5)

@router.get("/lexicon")
async def list_lexicon(): raise _NI(6)

@router.post("/lexicon", status_code=201)
async def create_lexicon_entry(): raise _NI(6)

@router.delete("/lexicon/{entry_id}")
async def delete_lexicon_entry(entry_id: str): raise _NI(6)
