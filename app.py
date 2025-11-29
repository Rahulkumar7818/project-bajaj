import os
import json
import requests
import tempfile
import google.generativeai as genai
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- CONFIGURATION ---
# Get this from https://aistudio.google.com/app/apikey
API_KEY = os.getenv("GOOGLE_API_KEY") 

if not API_KEY:
    print("❌ ERROR: GOOGLE_API_KEY not found in environment variables.")
else:
    genai.configure(api_key=API_KEY)

# --- GENERATION CONFIG ---
# This forces Gemini to output valid JSON
generation_config = {
    "temperature": 0.1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
    "response_mime_type": "application/json",
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash", # Flash is fast and cheap
    generation_config=generation_config,
)

# --- THE PROMPT ---
# This ensures the output matches your Hackathon constraints EXACTLY
SYSTEM_PROMPT = """
You are an expert automated Invoice Extraction System.
Your task is to extract line item details, sub-totals, and final totals from the provided bill/invoice image or PDF.

RULES:
1. Extract ALL line items. Do not miss any.
2. Do not double count items.
3. Return ONLY JSON. No markdown formatting.
4. Follow this exact structure for the output:

{
    "pagewise_line_items": [
        {
            "page_no": "1",
            "page_type": "Bill Detail", 
            "bill_items": [
                {
                    "item_name": "Exact Item Name",
                    "item_amount": 100.00,
                    "item_rate": 10.00,
                    "item_quantity": 10.0
                }
            ]
        }
    ],
    "total_item_count": 0
}

NOTE: 
- "item_amount" is the Net Amount (Rate * Qty).
- "page_type" should be "Bill Detail", "Final Bill", or "Pharmacy".
- If the document has multiple pages, group items by page.
"""

# --- ROUTE ---
@app.route('/extract-bill-data', methods=['POST'])
def extract_bill_data():
    # 1. Validate Input
    data = request.get_json()
    if not data or 'document' not in data:
        return jsonify({"is_success": False, "error": "Missing 'document' url"}), 400
    
    doc_url = data['document']
    
    temp_path = None
    try:
        # 2. Download the File
        # We need to save it temporarily to upload to Gemini
        print(f"📥 Downloading: {doc_url}")
        response = requests.get(doc_url, stream=True)
        if response.status_code != 200:
            return jsonify({"is_success": False, "error": "Failed to download document"}), 400

        # Determine extension (default to jpg if unknown, Gemini handles mime types well)
        ext = ".pdf" if ".pdf" in doc_url.lower() else ".jpg"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name

        # 3. Upload to Gemini File API
        # This handles large PDFs and Images natively
        print("📤 Uploading to Gemini...")
        uploaded_file = genai.upload_file(temp_path)
        
        # 4. Generate Content
        print("🧠 Processing with Gemini Flash...")
        response = model.generate_content([SYSTEM_PROMPT, uploaded_file])
        
        # 5. Parse Response
        ai_output = json.loads(response.text)
        
        # Calculate tokens (Gemini provides usage metadata)
        usage = response.usage_metadata
        token_usage = {
            "total_tokens": usage.total_token_count,
            "input_tokens": usage.prompt_token_count,
            "output_tokens": usage.candidates_token_count
        }

        # 6. Format Final Response
        final_response = {
            "is_success": True,
            "token_usage": token_usage,
            "data": ai_output
        }

        return jsonify(final_response)

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"is_success": False, "error": str(e)}), 500
    
    finally:
        # Cleanup temp file
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)