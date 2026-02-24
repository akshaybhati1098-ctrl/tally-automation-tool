from fastapi import FastAPI, Request, UploadFile, Form, HTTPException
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging

# Existing services
from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json

# ✅ NEW: Image → Excel service
from core.process_service import image_to_excel

app = FastAPI(title="Tally Automation Tool")

# -------------------------
# Static files & templates
# -------------------------
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# -------------------------
# UI (single entry point)
# -------------------------
@app.get("/")
async def serve_ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# =========================================================
# Excel → XML API
# =========================================================
@app.post("/api/convert")
async def convert_excel_api(
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale")
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only Excel files allowed")

    try:
        file_bytes = await file.read()
        xml_content, count = excel_to_xml(file_bytes, sheet_name, vtype)

        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": (
                    f"attachment; filename="
                    f"{file.filename.rsplit('.', 1)[0]}_output.xml"
                ),
                "X-Records-Processed": str(count)
            }
        )
    except Exception as e:
        logging.error(e)
        raise HTTPException(500, str(e))

# =========================================================
# Image / PDF → Excel API  ✅ NEW
# =========================================================
@app.post("/api/image-to-excel")
async def image_to_excel_api(
    file: UploadFile,
    company_key: str = Form(...)
):
    if not file.filename.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
        raise HTTPException(400, "Only PDF or image files allowed")

    try:
        file_bytes = await file.read()

        excel_bytes, output_filename = image_to_excel(
            file_bytes=file_bytes,
            original_filename=file.filename,
            company_key=company_key
        )

        return Response(
            content=excel_bytes,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": f"attachment; filename={output_filename}"
            }
        )

    except Exception as e:
        logging.error(e)
        raise HTTPException(500, str(e))

# =========================================================
# Mapping APIs
# =========================================================
@app.get("/api/mapping")
async def get_mapping():
    return JSONResponse(content=load_mapping_json())

@app.post("/api/mapping")
async def update_mapping(mapping: dict):
    save_mapping_json(mapping)
    return {"status": "success"}