from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse

app = FastAPI()

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Templates (HTML)
templates = Jinja2Templates(directory="web/templates")

# Home page
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# -------------------------
# API endpoints (placeholders)
# -------------------------

@app.get("/api/mapping")
def get_mapping():
    # Placeholder response to avoid 404
    return JSONResponse({
        "status": "ok",
        "message": "Mapping API ready",
        "data": []
    })