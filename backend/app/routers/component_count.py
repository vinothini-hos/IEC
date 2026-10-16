import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import component_count, models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/threads", tags=["draft-boq"])

MEDIA_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".csv": "text/csv",
    ".dxf": "application/dxf",
    ".dwg": "application/acad",
}


def _check_equipment(db: Session, thread_id: uuid.UUID, equipment_index: int):
    thread = db.query(models.Thread).filter_by(id=thread_id).first()
    if not thread:
        raise HTTPException(404, "Thread not found")
    items = (thread.extraction_result or {}).get("equipment_items") or []
    if not items:
        raise HTTPException(400, "No extraction result for this thread yet")
    if equipment_index < 0 or equipment_index >= len(items):
        raise HTTPException(400, "Invalid equipment_index")


@router.get("/{thread_id}/draft-boq")
def get_draft_boq(thread_id: uuid.UUID, equipment_index: int = 0):
    """Every drawing counted for this equipment item, each with its own counts."""
    return {"drawings": component_count.list_runs(thread_id, equipment_index)}


@router.post("/{thread_id}/draft-boq")
def upload_draft_boq_drawing(
    thread_id: uuid.UUID,
    equipment_index: int = Form(0),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload one .dwg / .dxf / .svg P&ID for this equipment item and count its
    components against the drawing's legend tables. Runs synchronously - big
    sheets can take minutes."""
    _check_equipment(db, thread_id, equipment_index)
    try:
        result = component_count.run(thread_id, equipment_index, file.filename or "", file.file.read())
    except component_count.DuplicateDrawing as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"result": result}


@router.put("/{thread_id}/draft-boq/{run_id}/count")
def edit_draft_boq_count(thread_id: uuid.UUID, run_id: str, payload: schemas.DraftBoqCountIn):
    """Correct one component's count in a drawing (count: null reverts it)."""
    try:
        result = component_count.set_count(thread_id, run_id, payload.index, payload.count)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"result": result}


@router.delete("/{thread_id}/draft-boq/{run_id}")
def delete_draft_boq_drawing(thread_id: uuid.UUID, run_id: str):
    if not component_count.delete_run(thread_id, run_id):
        raise HTTPException(404, "Drawing not found")
    return {"deleted": run_id}


@router.get("/{thread_id}/draft-boq/{run_id}/files/{name}")
def get_draft_boq_file(thread_id: uuid.UUID, run_id: str, name: str, download: bool = False):
    """A converted / check file of one drawing (check.svg, check.png, counts.csv ...)."""
    folder = component_count.run_dir(thread_id, run_id)
    if folder is None or name not in component_count.SERVED_FILES or not (folder / name).exists():
        raise HTTPException(404, "File not found")
    ext = name[name.rfind("."):]
    return FileResponse(
        folder / name,
        media_type=MEDIA_TYPES.get(ext, "application/octet-stream"),
        filename=name if download else None,
    )
