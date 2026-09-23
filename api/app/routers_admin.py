from fastapi import APIRouter
router = APIRouter(tags=["admin"])

@router.get("/docs")
async def list_docs():
    """Minimal admin list — in-memory doc tracking for T13 portal."""
    return {"docs": [], "note": "T13 admin portal — extend with Qdrant/DocStore integration"}
