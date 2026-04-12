"""Proposals route — proxies to Papyra proposals API."""
import base64
import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from app.middleware.auth_middleware import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/proposals", tags=["proposals"])

PAPYRA_API = "https://api.papyra.org"
PAPYRA_PASSWORD = "martin1234!"


@router.post("/generate")
async def generate_proposal(
    lob: str = Form(...),
    documents: List[UploadFile] = File(...),
    agency_info: str = Form(default=""),
    user_context: str = Form(default=""),
    brand_primary: str = Form(default="#1A3560"),
    brand_accent: str = Form(default="#C9901E"),
    current_user: User = Depends(get_current_user),
):
    """Proxy proposal generation to Papyra API."""
    files = []
    for doc in documents:
        content = await doc.read()
        files.append(("documents", (doc.filename or "document.pdf", content, "application/pdf")))

    data = {
        "password": PAPYRA_PASSWORD,
        "lob": lob,
        "agency_info": agency_info,
        "user_context": user_context,
        "brand_primary": brand_primary,
        "brand_accent": brand_accent,
    }

    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{PAPYRA_API}/api/proposals/external/generate",
                data=data,
                files=files,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response else str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=detail)
    except Exception as exc:
        logger.error("Papyra proxy failed: %s", exc)
        raise HTTPException(status_code=502, detail="Proposal service unavailable")
