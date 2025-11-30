import os
import json
import requests
import tempfile
import google.generativeai as genai
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- CONFIGURATION ---
API_KEY = os.getenv("GOOGLE_API_KEY") 

if not API_KEY:
    print("⚠️ WARNING: GOOGLE_API_KEY not found.")
else:
    genai.configure(api_key=API_KEY)

# --- GEMINI SETUP ---
generation_config = {
    "temperature": 0.0, # Set to 0 for maximum determinism
    "top_p": 0.95,
    "max_output_tokens": 8192,
    "response_mime_type": "application/json",
}

# Model: gemini-2.0-flash-lite
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash-lite", 
    generation_config=generation_config,
)

SYSTEM_PROMPT = """
Extract bill data into the following specific JSON structure.
Do not wrap the result in a parent 'data' key; output the pagewise object directly.

REQUIRED JSON STRUCTURE:
{
    "pagewise_line_items": [
        {
            "page_no": "1",
            "page_type": "Pharmacy",
            "bill_items": [
                {
                    "item_name": "Item Name",
                    "item_amount": 0.00,
                    "item_rate": 0.00,
                    "item_quantity": 0
                }
            ]
        }
    ],
    "total_item_count": 0
}

RULES:
1. 'item_amount' is the total cost for that line item (Rate * Qty).
2. 'item_quantity' should be a number (integer or float).
3. 'page_type' should detect the category (e.g., Pharmacy, Lab, Consultation).
4. Return ONLY raw JSON.
"""

def process_with_gemini(file_path):
    # Upload to Gemini File API
    uploaded_file = genai.upload_file(file_path)
    
    # Generate content
    response = model.generate_content([SYSTEM_PROMPT, uploaded_file])
    
    # Parse the text response
    try:
        ai_data = json.loads(response.text)
    except:
        # Fallback cleanup if model adds markdown blocks
        cleaned_text = response.text.replace("```json", "").replace("```", "")
        ai_data = json.loads(cleaned_text)
    
    # Extract usage details
    usage = response.usage_metadata
    token_usage = {
        "total_tokens": usage.total_token_count,
        "input_tokens": usage.prompt_token_count,
        "output_tokens": usage.candidates_token_count
    }
    
    return ai_data, token_usage

@app.route('/extract-bill-data', methods=['POST'])
def extract_bill_api():
    temp_path = None
    try:
        # 1. Parse Input
        data = request.get_json()
        if not data or 'document' not in data:
            return jsonify({
                "is_success": False,
                "message": "Missing 'document' url in request body"
            }), 400
        
        doc_url = data['document']

        # 2. Download File
        response = requests.get(doc_url, stream=True)
        if response.status_code != 200:
            return jsonify({
                "is_success": False,
                "message": "Failed to download document from URL"
            }), 400
            
        ext = ".pdf" if ".pdf" in doc_url.lower() else ".jpg"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name

        # 3. Process with AI
        ai_data, token_usage = process_with_gemini(temp_path)

        # 4. Construct Exact Response Layout
        # Python 3.7+ preserves insertion order, ensuring the layout matches your requirement.
        response_payload = {
            "is_success": True,
            "token_usage": token_usage,
            "data": ai_data
        }

        return jsonify(response_payload), 200

    except Exception as e:
        # Log the actual error for server debugging
        print(f"Server Error: {str(e)}")
        
        # Return the strictly requested error layout
        return jsonify({
            "is_success": False,
            "message": "Failed to process document. Internal server error occurred"
        }), 500

    finally:
        # Cleanup temp file
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)