from flask import Flask, request, render_template, jsonify
from logic import extract_data_from_image

app = Flask(__name__)

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/extract', methods=['POST'])
def extract_api():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400

    # Pass the file stream to logic
    result = extract_data_from_image(file)
    return jsonify(result)

if __name__ == '__main__':
    # Run locally
    app.run(debug=True, port=5000)