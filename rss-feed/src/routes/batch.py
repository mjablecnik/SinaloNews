from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.database import get_db
from src.data.models import Website
from src.data.schemas import BatchSummaryResponse
from src.services.batch_service import BatchProcessor

router = APIRouter(prefix="/api/batch", tags=["batch"])


def get_batch_processor(db: AsyncSession = Depends(get_db)) -> BatchProcessor:
    from src.main import get_processor
    return get_processor()


@router.post("/process", summary="Process all websites", response_model=BatchSummaryResponse)
async def process_all(
    db: AsyncSession = Depends(get_db),
    processor: BatchProcessor = Depends(get_batch_processor),
):
    result = await processor.process_all(db)
    return BatchSummaryResponse(**result)


@router.post(
    "/process/{website_id}",
    summary="Process single website",
    response_model=BatchSummaryResponse,
)
async def process_website(
    website_id: int,
    db: AsyncSession = Depends(get_db),
    processor: BatchProcessor = Depends(get_batch_processor),
):
    website = await db.get(Website, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")
    result = await processor.process_website(website, db)
    return BatchSummaryResponse(**result)
