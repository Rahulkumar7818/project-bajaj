# AI Bill Extraction System

## 📘 Overview
Hospitals, pharmacies, and clinics generate bills (PDFs/images) in hundreds of formats. Manual data entry is slow, error-prone, and expensive.  
This project automates bill extraction using **OCR + Google Gemini (LLM)** to produce structured JSON with numeric validations and protection against double-counting.

---

## 🚨 Problem Statement

### **Context & Pain**
- Medical/pharmacy bills appear in diverse, unstructured layouts.
- Manual typing leads to slow processing and frequent errors.
- Multi-page invoices often cause double-counting or missed entries.

### **What We Solve**
- Automatic extraction of:
  - Line items  
  - Quantities  
  - Rates  
  - Amounts  
  - Subtotals and final totals  
- Resistant to layout variations.
- Enforces strict numeric validation and JSON schema rules.

### **Target Users**
- Hospitals  
- Pharmacies  
- Insurance claim processors  
- Finance & audit teams  

---

## 🚀 Solution Overview

### **Key Features**
- Accepts **PDF or Image** files (single/multi-page).
- Optional OCR pre-processing (Tesseract or Google Vision).
- Uses **Google Gemini** multimodal reasoning for:
  - Layout analysis  
  - Page classification  
  - Table extraction  
  - Line-item structuring  
- Automatic consistency checks:
  - `amount == rate * quantity`
  - Float enforcement  
- Prevents **double-counting** across pages.
- Returns clean, validated **JSON** (strict schema).

### **Outputs**
- `pagewise_line_items`
- `total_item_count`
- `subtotal` (if present)
- `final_total`
- Strongly typed JSON response

---

## 🏗️ Technical Architecture

### **Components**
1. **Frontend**
   - Simple HTML/JS UI to upload files or provide document URLs.

2. **API Server**
   - Flask endpoints:
     - `/extract-bill-data`
     - `/analyze-file`
   - Handles downloads, MIME detection, and temp file storage.

3. **Cloud / Model**
   - Google Gemini (`google.generativeai`).
   - Multimodal document analysis + extraction.

4. **Storage (Optional)**
   - AWS S3 or Google Cloud Storage.
   - Store uploaded documents or historical results.

5. **Database (Optional)**
   - PostgreSQL or MongoDB.
   - Store parsed outputs, audit logs, and billing history.

6. **Monitoring & Logging**
   - Sentry or CloudWatch.
   - Tracks latency, exceptions, and payload metrics.

---

## 📊 Data Flow Diagram — Process Breakdown

1. User uploads a file or provides a URL → API endpoint `/extract-bill-data`.
2. Server downloads the file, detects MIME/extension, and creates a tempfile.
3. File is uploaded to **Gemini** via `genai.upload_file`.
4. Gemini receives a **SYSTEM_PROMPT** enforcing schema and extraction logic.
5. Gemini returns structured JSON (or textual JSON) → server parses + validates.
6. Post-processing:
   - Deduplication  
   - Double-counting prevention (cross-page comparisons)  
   - Subtotal and final total computation  
7. Final structured output returned to client or stored in DB.

---

## 🧰 Tech Stack

### **Cloud / Model**
- Google Gemini (via `google-generativeai`)

### **Backend**
- Python Flask

### **Libraries**
- `requests`
- `mimetypes`
- `tempfile`
- `google.generativeai`
- Optional OCR: **Tesseract** or **Google Vision**

### **Database (Optional)**
- PostgreSQL  
- MongoDB  

### **Frontend**
- HTML / JavaScript  
- Optional: React for richer UI

### **DevOps**
- GitHub Actions  
- Docker  

---

## 🔧 How to Run Locally

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your Gemini API key
export GOOGLE_API_KEY=your_api_key_here

### 3. Run the backend
python main.py

### 4. Send request
```
POST /extract-bill-data
{
  "file_url": "https://example.com/bill.pdf"
}
```
