from fastapi import FastAPI, Request, UploadFile, Form, HTTPException
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging

from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json

app = FastAPI(title="Tally Excel to XML Converter")

# Static + templates
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# UI
@app.get("/")
async def serve_ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ---------------- Excel → XML ----------------
@app.post("/api/convert")
async def convert_excel_api(
    file: UploadFile,                  # ✅ SAME NAME AS BEFORE
    sheet_name: str = Form(...),
    vtype: str = Form("sale")           # ✅ SAME NAME AS BEFORE
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
                "Content-Disposition": f"attachment; filename={file.filename}_output.xml",
                "X-Records-Processed": str(count)
            }
        )
    except Exception as e:
        logging.error(e)
        raise HTTPException(500, str(e))

# ---------------- Mapping APIs ----------------
@app.get("/api/mapping")
async def get_mapping():
    return JSONResponse(content=load_mapping_json())

@app.post("/api/mapping")
async def update_mapping(mapping: dict):
    save_mapping_json(mapping)
    return {"status": "success"}