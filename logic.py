import torch
import re
import pytesseract
import numpy as np
from PIL import Image
from transformers import AutoProcessor, AutoModelForTokenClassification

# --- GLOBAL MODEL LOADING (Loads once when server starts) ---
print("⏳ Loading AI Model... (This may take a minute)")
MODEL_ID = "nielsr/layoutlmv3-finetuned-cord"
device = "cpu" # Force CPU for Render Free Tier (GPU is too expensive)

try:
    processor = AutoProcessor.from_pretrained(MODEL_ID, apply_ocr=False)
    model = AutoModelForTokenClassification.from_pretrained(MODEL_ID)
    model.to(device)
    model.eval()
    print("✅ Model Loaded Successfully")
except Exception as e:
    print(f"❌ Model Load Error: {e}")

# --- HELPER FUNCTIONS ---
def normalize_box(box, width, height):
    return [
        int(1000 * (box[0] / width)),
        int(1000 * (box[1] / height)),
        int(1000 * (box[2] / width)),
        int(1000 * (box[3] / height)),
    ]

def clean_price(text):
    try:
        clean = re.sub(r'[^\d.,]', '', text)
        clean = clean.replace(',', '')
        clean = re.sub(r'\.\s+', '.', clean)
        if clean.count('.') > 1:
             clean = clean.replace('.', '', clean.count('.') - 1)
        return float(clean)
    except:
        return 0.0

def group_by_rows(words, boxes, labels, predictions, threshold=15):
    """Groups entities into horizontal rows."""
    elements = []
    for w, b, l, p in zip(words, boxes, labels, predictions):
        y_center = (b[1] + b[3]) / 2
        elements.append({'text': w, 'box': b, 'label': l, 'score': p, 'y_center': y_center})

    elements.sort(key=lambda x: x['y_center'])
    
    rows = []
    current_row = []
    if elements:
        current_row.append(elements[0])
        
    for i in range(1, len(elements)):
        curr = elements[i]
        prev = current_row[-1]
        if abs(curr['y_center'] - prev['y_center']) < threshold:
            current_row.append(curr)
        else:
            current_row.sort(key=lambda x: x['box'][0])
            rows.append(current_row)
            current_row = [curr]
            
    if current_row:
        current_row.sort(key=lambda x: x['box'][0])
        rows.append(current_row)
    return rows

# --- MAIN EXTRACTION FUNCTION ---
def extract_data_from_image(image_file):
    try:
        # Load Image
        image = Image.open(image_file).convert("RGB")
        width, height = image.size
        
        # 1. OCR
        ocr_df = pytesseract.image_to_data(image, output_type=pytesseract.Output.DATAFRAME)
        ocr_df = ocr_df.dropna(subset=['text'])
        ocr_df = ocr_df[ocr_df.text.str.strip().str.len() > 0]
        words = ocr_df['text'].tolist()
        boxes = [normalize_box([r['left'], r['top'], r['left']+r['width'], r['top']+r['height']], width, height) for _, r in ocr_df.iterrows()]

        if not words:
            return {"error": "No text detected in image"}

        # 2. AI Inference
        encoding = processor(image, words, boxes=boxes, return_tensors="pt", truncation=True, padding="max_length")
        for k,v in encoding.items(): encoding[k] = v.to(device)

        with torch.no_grad():
            outputs = model(**encoding)

        predictions = outputs.logits.argmax(-1).squeeze().tolist()
        input_ids = encoding.input_ids.squeeze().tolist()
        id2label = model.config.id2label
        tokenizer = processor.tokenizer
        
        # 3. Clean Tokens
        clean_words, clean_boxes, clean_labels, clean_scores = [], [], [], []
        for idx, token_id in enumerate(input_ids):
            if token_id in [0, 1, 2]: continue
            word = tokenizer.decode([token_id], clean_up_tokenization_spaces=False)
            if not word.strip(): continue
            
            clean_words.append(word.strip())
            clean_boxes.append(encoding.bbox.squeeze().tolist()[idx])
            clean_labels.append(id2label[predictions[idx]])
            clean_scores.append(outputs.logits.squeeze()[idx][predictions[idx]].item())

        # 4. Row Clustering
        rows = group_by_rows(clean_words, clean_boxes, clean_labels, clean_scores)
        
        final_items = []
        extracted = {"subtotal": 0.0, "tax": 0.0, "total": 0.0}

        for row in rows:
            row_text = " ".join([x['text'] for x in row])
            row_labels = [x['label'] for x in row]
            
            # Skip Headers
            if "Description" in row_text or "Date" in row_text or "Rate" in row_text: continue

            name_parts = []
            qty = 1.0
            prices = []
            
            for item in row:
                label = item['label'].upper()
                text = item['text']
                box = item['box']
                
                # Ignore Serial Numbers (Far Left)
                if box[0] < 50 and re.match(r'^\d+$', text): continue 

                if "MENU.NM" in label or ("O" in label and not re.match(r'[\d\.]+', text)):
                    if "/" not in text and ":" not in text: name_parts.append(text)

                if "MENU.CNT" in label or re.match(r'^\d+$', text):
                    try:
                        val = float(text)
                        if val.is_integer() and val < 1000 and 300 < box[0] < 800: qty = val
                    except: pass

                if "PRICE" in label or re.match(r'^\d+[\.,]\d{2}$', text):
                    p = clean_price(text)
                    if p > 0: prices.append(p)

                if "TOTAL.TOTAL_PRICE" in label: extracted["total"] = max(extracted["total"], clean_price(text))
                if "SUB_TOTAL.TAX_PRICE" in label: extracted["tax"] += clean_price(text)

            if len(name_parts) > 0 and len(prices) > 0:
                full_name = " ".join(name_parts).replace(" .", ".").strip()
                final_items.append({"name": full_name, "qty": qty, "price": max(prices)})
            
            if "Category Total" in row_text and prices:
                extracted["total"] = max(prices)

        # 5. Math
        sum_items = sum(i["price"] for i in final_items)
        final_total = extracted["total"] if extracted["total"] > 0 else sum_items
        final_subtotal = sum_items
        final_tax = extracted["tax"]
        
        if final_total > final_subtotal and final_tax == 0:
            diff = final_total - final_subtotal
            if diff < (final_subtotal * 0.4): final_tax = diff

        return {
            "success": True,
            "items": final_items,
            "summary": {
                "subtotal": round(final_subtotal, 2),
                "tax": round(final_tax, 2),
                "total": round(final_total, 2),
                "is_tax_added": final_tax > 0
            }
        }

    except Exception as e:
        return {"success": False, "error": str(e)}