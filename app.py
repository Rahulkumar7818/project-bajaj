import os
import json
import requests
import tempfile
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
    "temperature": 0.1,
    "top_p": 0.95,
    "max_output_tokens": 8192,
    "response_mime_type": "application/json",
}

# UPDATED: Using Gemini 2.0 Flash Lite based on your docs
# Model code: gemini-2.0-flash-lite
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash-lite", 
    generation_config=generation_config,
)

SYSTEM_PROMPT = """
You are an Invoice Extraction System. Extract line items, sub-totals, and final totals.
RULES:
1. Extract ALL line items.
2. Return ONLY JSON.
3. Follow this structure exactly:
{
    "pagewise_line_items": [
        {
            "page_no": "1",
            "page_type": "Bill Detail", 
            "bill_items": [
                {
                    "item_name": "string",
                    "item_amount": 0.0,
                    "item_rate": 0.0,
                    "item_quantity": 0.0
                }
            ]
        }
    ],
    "total_item_count": 0
}
Note: item_amount is the net amount (rate * qty).
"""

# --- HELPER TO PROCESS FILE WITH GEMINI ---
def process_with_gemini(file_path):
    print("📤 Uploading to Gemini...")
    # Gemini 2.0 Flash Lite supports Images/PDFs via File API
    uploaded_file = genai.upload_file(file_path)
    
    print(f"🧠 Analyzing with {model.model_name}...")
    response = model.generate_content([SYSTEM_PROMPT, uploaded_file])
    
    # Parse JSON
    try:
        ai_output = json.loads(response.text)
    except Exception as e:
        # Fallback if model returns text + json
        print(f"JSON Parse Error: {e}. Raw: {response.text}")
        cleaned_text = response.text.replace("```json", "").replace("```", "")
        ai_output = json.loads(cleaned_text)
    
    # Get Usage
    usage = response.usage_metadata
    token_usage = {
        "total_tokens": usage.total_token_count,
        "input_tokens": usage.prompt_token_count,
        "output_tokens": usage.candidates_token_count
    }
    
    return {
        "is_success": True,
        "token_usage": token_usage,
        "data": ai_output
    }

# --- ROUTES ---

@app.route('/')
def index():
    """Serves the Frontend UI"""
    return render_template('index.html')

@app.route('/extract-bill-data', methods=['POST'])
def extract_bill_api():
    """
    STRICT HACKATHON ENDPOINT
    Input: JSON {"document": "url"}
    """
    try:
        data = request.get_json()
        if not data or 'document' not in data:
            return jsonify({"is_success": False, "error": "Missing 'document' url"}), 400
        
        doc_url = data['document']
        print(f"📥 API Request for URL: {doc_url}")

        # Download URL to temp file
        response = requests.get(doc_url, stream=True)
        if response.status_code != 200:
            return jsonify({"is_success": False, "error": "Could not download file"}), 400
            
        ext = ".pdf" if ".pdf" in doc_url.lower() else ".jpg"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name

        try:
            result = process_with_gemini(temp_path)
            return jsonify(result)
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)

    except Exception as e:
        return jsonify({"is_success": False, "error": str(e)}), 500

@app.route('/analyze-file', methods=['POST'])
def analyze_file_ui():
    """
    UI HELPER ENDPOINT
    Input: Multipart File Upload
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    try:
        # Save uploaded file to temp
        ext = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            file.save(temp_file.name)
            temp_path = temp_file.name

        try:
            result = process_with_gemini(temp_path)
            return jsonify(result)
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)