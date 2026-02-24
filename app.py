from fastapi import FastAPI, UploadFile, Form, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json
import logging

app = FastAPI(title="Tally Excel to XML Converter")

# Mount static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Set up Jinja2 templates
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def serve_ui(request: Request):
    """Serve the main HTML page using templates."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/convert")
async def convert_excel(
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale")
):
    """Convert uploaded Excel file to Tally XML."""
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Only Excel files (.xlsx, .xls) are allowed")

    try:
        file_bytes = await file.read()
        xml_content, count = excel_to_xml(file_bytes, sheet_name, vtype)

        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": f"attachment; filename={file.filename.replace('.xlsx', '').replace('.xls', '')}_output.xml",
                "X-Records-Processed": str(count)
            }
        )
    except Exception as e:
        logging.error(f"Conversion failed: {e}")
        raise HTTPException(500, f"Conversion failed: {str(e)}")

@app.get("/api/mapping")
async def get_mapping():
    """Return the current mapping JSON."""
    try:
        mapping = load_mapping_json()
        return JSONResponse(content=mapping)
    except Exception as e:
        raise HTTPException(500, f"Failed to load mapping: {str(e)}")

@app.post("/api/mapping")
async def update_mapping(mapping: dict):
    """Save the updated mapping JSON."""
    try:
        save_mapping_json(mapping)
        return {"status": "success", "message": "Mapping saved"}
    except Exception as e:
        raise HTTPException(500, f"Failed to save mapping: {str(e)}")