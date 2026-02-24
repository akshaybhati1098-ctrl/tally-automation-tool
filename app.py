from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
import os
import shutil
import traceback

# 🔹 IMPORT YOUR CORE LOGIC
# Adjust file / function name if needed
from core.excel_to_xml import convert_excel_to_xml

app = FastAPI()

# -------------------------
# Static & Templates
# -------------------------
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# -------------------------
# Home Page
# -------------------------
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# -------------------------
# Mapping API (placeholder)
# -------------------------
@app.get("/api/mapping")
def get_mapping():
    return JSONResponse({
        "status": "ok",
        "data": []
    })

# -------------------------
# Excel → XML Converter API
# -------------------------
@app.post("/api/convert")
async def convert_excel(
    excel_file: UploadFile = File(...),
    sheet_name: str = Form(...),
    voucher_type: str = Form(...)
):
    try:
        # Ensure temp folder exists
        os.makedirs("/tmp", exist_ok=True)

        # Save uploaded Excel file
        input_path = f"/tmp/{excel_file.filename}"
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(excel_file.file, buffer)

        # Call CORE logic
        xml_output = convert_excel_to_xml(
            excel_path=input_path,
            sheet_name=sheet_name,
            voucher_type=voucher_type
        )

        return JSONResponse({
            "status": "success",
            "message": "XML generated successfully",
            "xml": xml_output
        })

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )