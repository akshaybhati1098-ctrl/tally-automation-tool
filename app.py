from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.responses import Response, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json
import logging

app = FastAPI(title="Tally Excel to XML Converter")

# Serve static files (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_ui():
    """Serve the main HTML page."""
    return FileResponse("static/index.html")

@app.post("/api/convert")
async def convert_excel(
    file: UploadFile,
    sheet_name: str = Form(...),
    vtype: str = Form("sale")
):
    """
    Convert uploaded Excel file to Tally XML.
    Returns the XML file with a custom header X-Records-Processed.
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Only Excel files (.xlsx, .xls) are allowed")

    try:
        file_bytes = await file.read()
        xml_content, count = excel_to_xml(file_bytes, sheet_name, vtype)

        # Return XML as downloadable file
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

# ---------- Mapping endpoints for the web editor ----------
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