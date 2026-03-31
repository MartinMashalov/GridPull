"""
Form filling routes.

POST /form-filling/fill  — upload a target PDF form + source files, returns filled PDF
"""

import logging
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response

from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.services.form_filling import PDFPopulator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/form-filling", tags=["form-filling"])

_ALLOWED_SOURCE_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".txt", ".md", ".markdown"}


@router.post("/fill")
async def fill_form(
    target_form: UploadFile = File(...),
    source_files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload a target PDF form and source files. Returns the filled PDF."""
    if not current_user.stripe_payment_method_id:
        raise HTTPException(
            status_code=402,
            detail={"type": "card_required", "message": "A credit card is required to use this feature. Add one in Settings."},
        )

    target_name = (target_form.filename or "").lower()
    if not target_name.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Target form must be a PDF file")

    target_bytes = await target_form.read()
    if not target_bytes:
        raise HTTPException(status_code=400, detail="Target form file is empty")

    source_data: list[tuple[str, bytes]] = []
    for sf in source_files:
        fname = sf.filename or "unknown"
        ext = os.path.splitext(fname.lower())[1]
        if ext not in _ALLOWED_SOURCE_EXTS:
            logger.warning("Skipping unsupported source file: %s", fname)
            continue
        content = await sf.read()
        if content:
            source_data.append((fname, content))

    if not source_data:
        raise HTTPException(status_code=400, detail="No valid source files provided")

    logger.info(
        "Form fill request — user_id=%s target=%s sources=%d",
        current_user.id, target_form.filename, len(source_data),
    )

    try:
        populator = PDFPopulator()
        filled_pdf, cost, model_breakdown = await populator.populate_async(source_data, target_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Form filling failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Form filling failed — please try again")

    logger.info("Form fill complete — user_id=%s cost=$%.6f size=%d bytes", current_user.id, cost, len(filled_pdf))

    output_name = f"filled_{target_form.filename or 'form.pdf'}"
    return Response(
        content=filled_pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{output_name}"'},
    )
