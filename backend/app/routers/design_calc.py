import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import design_calc, models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/threads", tags=["design-calc"])


@router.get("/{thread_id}/design-calc")
def get_design_calc(thread_id: uuid.UUID, equipment_index: int = 0):
    """Last-saved design calc result for this equipment item, if one was ever
    run — doesn't run a fresh calculation (see POST)."""
    return {"result": design_calc.load_result(thread_id, equipment_index)}


@router.post("/{thread_id}/design-calc")
def run_design_calc(
    thread_id: uuid.UUID, payload: schemas.DesignCalcIn, db: Session = Depends(get_db)
):
    """Run every design calc sheet against the extracted equipment item's
    fields, saving the computed values and one .xlsx per sheet."""
    thread = db.query(models.Thread).filter_by(id=thread_id).first()
    if not thread:
        raise HTTPException(404, "Thread not found")

    result_data = thread.extraction_result
    if not result_data or not result_data.get("equipment_items"):
        raise HTTPException(400, "No extraction result for this thread yet")

    items = result_data["equipment_items"]
    if payload.equipment_index < 0 or payload.equipment_index >= len(items):
        raise HTTPException(400, "Invalid equipment_index")

    return {
        "result": design_calc.run_for_equipment(
            thread_id, payload.equipment_index, items[payload.equipment_index]
        )
    }


@router.put("/{thread_id}/design-calc/cell")
def edit_design_calc_cell(thread_id: uuid.UUID, payload: schemas.DesignCalcCellIn):
    """Set (or revert, with an empty value) one cell's value. Saved in the
    result right away; dependent cells update on the next calculation."""
    try:
        result = design_calc.set_cell(
            thread_id, payload.equipment_index, payload.sheet_key,
            payload.table_id, payload.row_id, payload.key, payload.value,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"result": result}


@router.get("/{thread_id}/design-calc/xlsx")
def download_design_calc_xlsx(thread_id: uuid.UUID, equipment_index: int = 0):
    """One workbook with every design calc sheet of the last run."""
    path = design_calc.xlsx_path(thread_id, equipment_index)
    if path is None:
        raise HTTPException(404, "No workbook yet — run the calculation first")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="design_calculation.xlsx",
    )
