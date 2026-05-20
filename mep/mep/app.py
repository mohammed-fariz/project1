from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import os
from dotenv import load_dotenv
from openai import OpenAI

# ===============================
# LOAD ENV
# ===============================
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("❌ OPENAI_API_KEY not found")

# ===============================
# INIT APP
# ===============================
app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=api_key)

# ===============================
# HOME
# ===============================
@app.route("/")
def home():
    return render_template("index.html")

# ===============================
# CLEAN OUTPUT
# ===============================
def clean_json(text):
    text = text.replace("```json", "").replace("```", "").strip()
    return text

# ===============================
# ANALYSIS FUNCTION
# ===============================
def analyze_input(input_json):

    prompt = f"""
You are a strict MEP validation and risk assessment system.

INPUT:
{json.dumps(input_json, indent=2)}

----------------------------------------
STEP 1: USE ONLY GIVEN DATA
- Do NOT guess
- Do NOT assume missing values

----------------------------------------
STEP 2: APPLY ENGINEERING THRESHOLD RULES

Evaluate each parameter:

- load_kN > 10 → high load risk
- spacing_m > 1.5 → spacing risk
- edge_distance_mm < 100 → pull-out risk
- safety_factor < 1.5 → unsafe condition
- environment == outdoor → corrosion risk

----------------------------------------
STEP 3: RISK DECISION

- 0–1 issues → Low risk
- 2–3 issues → Medium risk
- ≥4 issues → High risk

----------------------------------------
STEP 4: SCORING

- Low → 0.1–0.3
- Medium → 0.4–0.7
- High → 0.7–1.0

----------------------------------------
STEP 5: OUTPUT

Return ONLY JSON:

{{
  "failure_risk_score": float,
  "failure_probability": "Low/Medium/High",
  "failure_type": "Consistent / Inconsistency",
  "status": "Safe / Unsafe",
  "reason": "short sentence (max 12 words)"
}}
"""

    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.choices[0].message.content
    cleaned = clean_json(raw)

    return json.loads(cleaned)

# ===============================
# API ROUTE
# ===============================
@app.route("/predict", methods=["POST"])
def predict():

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    if not file.filename.endswith(".json"):
        return jsonify({"error": "Only JSON files allowed"}), 400

    try:
        data = json.load(file)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if not isinstance(data, list):
        data = [data]

    results = []
    errors = []

    for i, item in enumerate(data):
        try:
            output = analyze_input(item)

            results.append({
                "index": i + 1,
                "input": item,
                "output": output
            })

        except Exception as e:
            errors.append({
                "index": i + 1,
                "error": str(e)
            })

    return jsonify({
        "total": len(data),
        "success": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors
    })

# ===============================
# HEALTH
# ===============================
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    app.run(debug=True, port=5000)