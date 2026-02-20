from fastapi import FastAPI, UploadFile, Form, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging
import os

from core.excel_service import excel_to_xml
from core.mapping import load_mapping_json, save_mapping_json
from core.company_rules import load_rules, save_rules
from core.process_service import image_to_excel

app = FastAPI(title="Tally Excel to XML Converter")

# ✅ FIXED PATHS
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")
