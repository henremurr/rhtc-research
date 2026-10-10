from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from scripts.build_user_guide_pdf import build_pdf

router = APIRouter(prefix="/api/user-guide", tags=["user-guide"])
GUIDE_PATH = Path(__file__).resolve().parents[2] / "USER_GUIDE.md"


@router.get("/pdf")
def create_user_guide_pdf(download: bool = Query(default=False)) -> Response:
    """Build a fresh printable PDF from the current Markdown user guide."""
    if not GUIDE_PATH.is_file():
        raise HTTPException(503, "The user guide is not available in this deployment.")

    descriptor, filename = tempfile.mkstemp(prefix="rhtc-user-guide-", suffix=".pdf")
    os.close(descriptor)
    pdf_path = Path(filename)
    try:
        build_pdf(source=GUIDE_PATH, output=pdf_path)
        payload = pdf_path.read_bytes()
    except Exception as exc:
        raise HTTPException(500, "Could not generate the user guide PDF.") from exc
    finally:
        pdf_path.unlink(missing_ok=True)

    disposition = "attachment" if download else "inline"
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="RHTC_User_Guide.pdf"'},
    )
