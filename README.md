---
title: Tally Automation
emoji: 📊
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

# Akshay's Tally Tool

A FastAPI-based automation tool inspired by Tally workflows.

## Features

- ✅ Excel → Tally XML conversion  
- ✅ PDF / Image → Excel (OCR powered)  
- ✅ Company-wise rules engine  
- ✅ Mapping editor for ledgers & vouchers  
- ✅ Web UI + REST API  

## Tech Stack

- **Backend**: FastAPI
- **OCR**: Tesseract OCR
- **PDF Processing**: Poppler
- **Container**: Docker (Hugging Face Space)

## Endpoints

- `/` – Web UI  
- `/docs` – Swagger API documentation  
- `/api/convert` – Excel to XML  
- `/api/convert-image` – PDF/Image to Excel  
- `/api/mapping` – Ledger mapping  
- `/api/company-rules` – Company rules  

## Notes

- This Space runs using **Docker SDK**
- System dependencies like `poppler-utils` and `tesseract-ocr`
  are installed via `Dockerfile`
- Port `7860` is used as required by Hugging Face

---

🚀 Built for accountants & automation workflows.
