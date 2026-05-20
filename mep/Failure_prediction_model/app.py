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
- Do NOT introduce new materials, components, or parameters
- Use ONLY fields explicitly present in the input

----------------------------------------
STEP 2: DATA VALIDATION (CRITICAL LAYER)

Check input quality BEFORE applying rules:

1. MISSING DATA CHECK
- If required fields are null / missing → mark as "Insufficient Data"
- Missing critical values (airflow, return, load, etc.) increase risk

2. INVALID VALUE CHECK
- Negative values → invalid
- Zero values where not applicable → invalid

3. MATERIAL / SIZE VALIDATION
- Check if sizes (duct_diameter, grille_size, etc.) are present
- If size is null or inconsistent → mark as "Invalid Data"
- DO NOT assume correct size
- DO NOT replace or fix values

4. CONSISTENCY CHECK
- Compare related fields (if available)
- If mismatch → inconsistency

----------------------------------------
STEP 3: APPLY ENGINEERING THRESHOLD RULES

Apply ONLY if data is available:

- load_kN > 10 → high load risk
- spacing_m > 1.5 → spacing risk
- edge_distance_mm < 100 → pull-out risk
- safety_factor < 1.5 → unsafe condition
- environment == outdoor → corrosion risk

IMPORTANT:
- If a parameter is missing → SKIP rule (do NOT assume)

----------------------------------------
STEP 4: RISK DECISION

Combine:
- Validation issues (missing / invalid data)
- Engineering rule violations

Rules:

- 0–1 issues → Low risk
- 2–3 issues → Medium risk
- ≥4 issues → High risk

----------------------------------------
STEP 5: SCORING (CONFIDENCE-AWARE)

- Low → 0.1–0.3
- Medium → 0.4–0.7
- High → 0.7–1.0

SCORING ADJUSTMENT:

- Missing critical data → increase risk score
- Invalid sizes / null values → increase risk score
- Complete and valid data → lower risk score

----------------------------------------
STEP 6: FAILURE TYPE LOGIC

- Missing data → "Insufficient Data"
- Invalid values → "Invalid Data"
- Rule violations → "Inconsistency"
- No issues → "Consistent"

----------------------------------------
STEP 7: STATUS

- Safe → if Low risk AND valid data
- Unsafe → if High risk
- Insufficient Data → if validation fails

----------------------------------------
STEP 8: OUTPUT RULES

- Do NOT mention any new materials not in input
- Do NOT suggest adding components
- Do NOT infer missing values
- Reason must ONLY refer to observed input issues

----------------------------------------
STEP 9: OUTPUT FORMAT (STRICT JSON ONLY)

{{
  "failure_risk_score": float,
  "failure_probability": "Low/Medium/High",
  "failure_type": "Consistent / Inconsistency / Invalid Data / Insufficient Data",
  "status": "Safe / Unsafe / Insufficient Data",
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