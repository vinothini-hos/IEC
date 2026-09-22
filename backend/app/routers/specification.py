import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import clarification_service, extraction, models, rag_service, schemas, template_consolidation
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/api/threads", tags=["specification"])


def _find_latest_file(out_dir: Path, prefix: str):
    """Return the most recently written storage/ file matching
    <prefix>-<timestamp>-<thread_id>.json, or None if there isn't one yet.
    Uses mtime rather than parsing the embedded timestamp, since the
    DDMMYYYY_HHMMSS format doesn't sort correctly lexicographically across
    month boundaries."""
    if not out_dir.is_dir():
        return None
    candidates = list(out_dir.glob(f"{prefix}-*.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


@router.get("/{thread_id}/specification")
def get_specification(thread_id: uuid.UUID, db: Session = Depends(get_db)):
    thread = db.query(models.Thread).filter_by(id=thread_id).first()
    if not thread:
        raise HTTPException(404, "Thread not found")
    return {"status": thread.extraction_status, "result": thread.extraction_result}


@router.post("/{thread_id}/extract")
def extract(thread_id: uuid.UUID, db: Session = Depends(get_db)):
    """Run the Spec Extraction pipeline (equipment identification, then
    per-field template consolidation with status classification), and
    persist the result on the thread for the Spec Extraction page."""
    thread = (
        db.query(models.Thread)
        .options(joinedload(models.Thread.emails).joinedload(models.Email.attachments))
        .filter(models.Thread.id == thread_id)
        .first()
    )
    if not thread:
        raise HTTPException(404, "Thread not found")

    try:
        requested_equipments = extraction.extract_specification_for_thread(thread)
    except Exception as e:
        raise HTTPException(500, f"Extraction failed: {e}")
    extraction.save_specification_result(thread_id, requested_equipments)

    try:
        equipment_items = template_consolidation.run_data_extraction_for_thread(
            thread, requested_equipments
        )
    except Exception as e:
        raise HTTPException(500, f"Template consolidation failed: {e}")

    result = {
        "classification_summary": (
            equipment_items[0]["classification_label"] if equipment_items else None
        ),
        "equipment_items": equipment_items,
    }
    thread.extraction_result = result
    thread.extraction_status = "extracted"
    db.commit()

    return {"status": thread.extraction_status, "result": result}


@router.post("/{thread_id}/clarification")
def send_clarification(
    thread_id: uuid.UUID, payload: schemas.ClarificationIn, db: Session = Depends(get_db)
):
    thread = db.query(models.Thread).filter_by(id=thread_id).first()
    if not thread:
        raise HTTPException(404, "Thread not found")

    try:
        return clarification_service.send_clarification(db, thread, payload.equipment_index)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to send clarification: {e}")


@router.get("/{thread_id}/similar-projects")
def get_similar_projects(thread_id: uuid.UUID, equipment_index: int = 0, db: Session = Depends(get_db)):
    """Returns the last-saved similar-projects result for this equipment
    item, if one was ever run — doesn't run a fresh search (see POST)."""
    thread = db.query(models.Thread).filter_by(id=thread_id).first()
    if not thread:
        raise HTTPException(404, "Thread not found")

    type_label = None
    result_data = thread.extraction_result
    if result_data and result_data.get("equipment_items"):
        items = result_data["equipment_items"]
        if 0 <= equipment_index < len(items):
            type_label = items[equipment_index].get("type_label")

    out_dir = Path(settings.similar_projects_storage_dir) / str(thread_id)
    path = _find_latest_file(out_dir, f"{equipment_index}_{type_label or 'unknown'}")
    if path is None:
        return {"result": None}
    return {"result": json.loads(path.read_text())}


@router.post("/{thread_id}/similar-projects")
def similar_projects(
    thread_id: uuid.UUID, payload: schemas.SimilarProjectsIn, db: Session = Depends(get_db)
):
    """Vector-search + LLM-rerank past projects of the same equipment type
    as the given equipment item, and save the result as JSON on disk."""
    thread = db.query(models.Thread).filter_by(id=thread_id).first()
    if not thread:
        raise HTTPException(404, "Thread not found")

    result_data = thread.extraction_result
    if not result_data or not result_data.get("equipment_items"):
        raise HTTPException(400, "No extraction result for this thread yet")

    items = result_data["equipment_items"]
    if payload.equipment_index < 0 or payload.equipment_index >= len(items):
        raise HTTPException(400, "Invalid equipment_index")

    try:
        result = rag_service.find_similar_projects(items[payload.equipment_index])
    except Exception as e:
        raise HTTPException(500, f"Similar projects search failed: {e}")

    saved_path = rag_service.save_similar_projects_result(thread_id, payload.equipment_index, result)
    return {"saved_path": saved_path, **result}