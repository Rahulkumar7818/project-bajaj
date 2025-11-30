import os
import json
import requests
import tempfile
import mimetypes
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# --- CONFIGURATION ---
API_KEY = os.getenv("GOOGLE_API_KEY") 

if not API_KEY:
    print("⚠️ WARNING: GOOGLE_API_KEY not found.")
else:
    genai.configure(api_key=API_KEY)

# --- GEMINI SETUP ---
generation_config = {
    "temperature": 0.0,
    "top_p": 0.95,
    "max_output_tokens": 8192,
    "response_mime_type": "application/json",
}

model = genai.GenerativeModel(
    model_name="gemini-2.0-flash-lite", 
    generation_config=generation_config,
)

# --- IMPROVED SYSTEM PROMPT ---
# Changes:
# 1. Enforced float types for quantity/rates as per requirement.
# 2. Added logic to prevent Double Counting (Evaluation Criteria).
# 3. Defined Page Type logic.
SYSTEM_PROMPT = """
You are an expert Medical Bill Extractor. 
Extract data strictly into this JSON structure.

REQUIRED OUTPUT JSON:
{
    "pagewise_line_items": [
        {
            "page_no": "string (e.g. '1')",
            "page_type": "string (Value must be one of: 'Bill Detail', 'Final Bill', 'Pharmacy')",
            "bill_items": [
                {
                    "item_name": "string",
                    "item_amount": 0.00,
                    "item_rate": 0.00,
                    "item_quantity": 0.00
                }
            ]
        }
    ],
    "total_item_count": 0
}

EXTRACTION RULES:
1. **Types**: 'item_quantity' and 'item_rate' MUST be floats (e.g., 1.0, 5.5).
2. **Calculations**: 'item_amount' = (item_rate * item_quantity).
3. **Page Categories**:
   - "Pharmacy": Pages listing medicines.
   - "Bill Detail": Pages listing hospital services/charges.
   - "Final Bill": Summary pages showing totals.
4. **NO DOUBLE COUNTING**: 
   - Extract individual line items from "Pharmacy" or "Bill Detail" pages.
   - ONLY extract from "Final Bill" (Summary) pages if those specific items were NOT listed on previous detailed pages.
   - Do not extract a "Total" line as an item.
"""

def process_with_gemini(file_path, mime_type):
    uploaded_file = None
    try:
        # Upload
        uploaded_file = genai.upload_file(file_path, mime_type=mime_type)
        
        # Generate
        response = model.generate_content([SYSTEM_PROMPT, uploaded_file])
        
        # Parse
        try:
            ai_data = json.loads(response.text)
        except:
            cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
            ai_data = json.loads(cleaned_text)
        
        # Usage
        usage = response.usage_metadata
        token_usage = {
            "total_tokens": usage.total_token_count,
            "input_tokens": usage.prompt_token_count,
            "output_tokens": usage.candidates_token_count
        }
        
        return {
            "is_success": True,
            "token_usage": token_usage,
            "data": ai_data
        }
    finally:
        # GOOD PRACTICE: Delete file from Gemini Cloud to avoid clutter/limits
        if uploaded_file:
            try:
                uploaded_file.delete()
            except:
                pass

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract-bill-data', methods=['POST'])
def extract_bill_api():
    temp_path = None
    try:
        data = request.get_json()
        if not data or 'document' not in data:
            return jsonify({"is_success": False, "message": "Missing 'document' url"}), 400
        
        doc_url = data['document']
        
        # Download
        response = requests.get(doc_url, stream=True)
        if response.status_code != 200:
            return jsonify({"is_success": False, "message": "Download failed"}), 400
        
        # Robust MIME Type Detection
        content_type = response.headers.get('Content-Type', '')
        ext = mimetypes.guess_extension(content_type)
        if not ext:
            # Fallback checks if headers fail
            if '.pdf' in doc_url.lower(): ext = '.pdf'
            elif '.png' in doc_url.lower(): ext = '.png'
            elif '.jpg' in doc_url.lower(): ext = '.jpg'
            else: ext = '.pdf' # Default
            
        # Determine MIME for Gemini
        gemini_mime_type = content_type if content_type else 'application/pdf'
        if ext == '.pdf': gemini_mime_type = 'application/pdf'
        if ext in ['.png', '.jpg', '.jpeg']: gemini_mime_type = 'image/jpeg'

        # Save Temp
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name

        try:
            result = process_with_gemini(temp_path, gemini_mime_type)
            return jsonify(result)
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)

    except Exception as e:
        # Return strict error format
        return jsonify({"is_success": False, "message": str(e)}), 500

@app.route('/analyze-file', methods=['POST'])
def analyze_file_ui():
    """Helper for UI testing"""
    if 'file' not in request.files:
        return jsonify({"is_success": False, "error": "No file"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"is_success": False, "error": "No file"}), 400

    try:
        mime_type = file.content_type or 'application/pdf'
        ext = mimetypes.guess_extension(mime_type) or ".pdf"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            file.save(temp_file.name)
            temp_path = temp_file.name

        try:
            result = process_with_gemini(temp_path, mime_type)
            return jsonify(result)
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)
    except Exception as e:
        return jsonify({"is_success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)