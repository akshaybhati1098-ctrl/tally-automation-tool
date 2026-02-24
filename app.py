from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse

# ✅ IMPORT THE CORRECT SERVICE
from core.excel_service import excel_to_xml

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
    return {
        "status": "ok",
        "data": []
    }

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
        # 1️⃣ Read uploaded file as bytes
        file_bytes = await excel_file.read()

        # 2️⃣ Call your EXISTING core logic
        xml_content, record_count = excel_to_xml(
            file_bytes=file_bytes,
            sheet_name=sheet_name,
            vtype=voucher_type
        )

        # 3️⃣ Return response
        return JSONResponse({
            "status": "success",
            "records": record_count,
            "xml": xml_content
        })

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e)
            }
        )