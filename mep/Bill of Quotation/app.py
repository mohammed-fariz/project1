# from flask import Flask, request, jsonify, render_template
# from flask_cors import CORS
# import json
# import os
# from dotenv import load_dotenv
# from openai import OpenAI

# # ================================================================
# # ENVIRONMENT SETUP
# # ================================================================
# load_dotenv()
# api_key = os.getenv("OPENAI_API_KEY")

# if not api_key:
#     raise ValueError("❌ OPENAI_API_KEY not found")

# # ================================================================
# # FLASK APP INITIALIZATION
# # ================================================================
# app = Flask(__name__)
# CORS(app)

# # ================================================================
# # OPENAI CLIENT
# # ================================================================
# client = OpenAI(api_key=api_key)

# # ================================================================
# # SYSTEM PROMPT (PROFESSIONALLY STRUCTURED)
# # ================================================================
# SYSTEM_PROMPT = """
# You are an advanced MEP BOQ (Bill of Quantities) estimation system.

# Your task is to analyze structured input data and generate a BOQ by extracting elements, estimating quantities, and calculating costs in a consistent and controlled manner.

# ----------------------------------------
# INPUT DATA:
# {{input_json}}
# ----------------------------------------

# 🔍 INPUT UNDERSTANDING

# - Carefully analyze the structure of the input
# - Identify:
#   • Available elements (e.g., ducts, pipes, cables, fittings, equipment)
#   • Material rates
#   • Any quantity-driving parameters (e.g., floor area, counts, lengths)

# - Allow equivalent field interpretation:
#   • e.g., floor_area_sqft → floor_area

# IMPORTANT:
# - Use ONLY the data present in the input
# - Do NOT assume completely missing information
# - Do NOT introduce new elements

# ----------------------------------------
# 🧠 ELEMENT PROCESSING

# - Process ONLY elements explicitly present in the input
# - Maintain logical grouping of elements
# - Do NOT expand categories into new components

# 🚫 EQUIPMENT RULE:
# - Include equipment ONLY if explicitly defined in the input
# - Otherwise, skip it entirely

# ----------------------------------------
# 📐 QUANTITY ESTIMATION (CONTROLLED & GENERIC)

# - If a driving parameter (e.g., area, count, length) is available:
#   → derive quantities using simple proportional relationships

# - If quantities are already provided:
#   → use them directly

# - If data is insufficient:
#   → perform minimal estimation without assumptions

# ----------------------------------------
# 🔢 QUANTITY RULES

# - All quantities MUST be integers
# - Decimal values are NOT allowed

# Rounding:
# - ≥ 0.5 → round up
# - < 0.5 → round down

# ----------------------------------------
# 💰 COST CALCULATION

# - Use ONLY material_rates from input
# - Map elements directly to available rates

# - total_cost = quantity × unit_rate

# ----------------------------------------
# 🚨 STRICT VALIDATION (CRITICAL FIX)

# - NOT ALL material_rates are valid automatically

# - For ducts:
#   ONLY these sizes are considered VALID:
#     • duct_10x6_per_meter
#     • duct_12x6_per_meter

# - ANY other duct size (e.g., duct_15x7_per_meter) is INVALID

# INVALID HANDLING:
# - If duct rate is NOT in valid list:
#   → DO NOT use it
#   → set:
#       unit_rate = 0
#       total_cost = 0
#       size = "unknown"

# ----------------------------------------
# ⚠️ VALIDATION & ERROR HANDLING

# - Validate consistency between elements and rates

# - If invalid or unsupported data is detected:
#   → skip or neutralize affected item (set cost = 0)
#   → continue processing remaining elements

# - Do NOT stop execution due to partial errors
# ⚠️ VALIDATION LAYER (NEW — CRITICAL)

# After computing, evaluate output using:

# 1. CALCULATIONS
#    ✔ Check arithmetic correctness

# 2. LOGIC CONSISTENCY
#    ✔ Are values derived from input OR estimated clearly?

# 3. RULE ADHERENCE
#    ✔ Did system follow "use input first" rule?

# 4. CONFIDENCE SCORE VALIDITY
#    ✔ Does confidence reflect:
#      - missing data
#      - estimation usage
#      - inconsistencies

# 5. REMARK QUALITY
#    ✔ Must clearly state:
#      - estimation used OR
#      - missing data OR
#      - unit mismatch

# ----------------------------------------
# 📊 OUTPUT GENERATION

# - Generate structured JSON dynamically based on input
# - Include ONLY elements that exist in input

# For each element include:
#   • quantity / length
#   • unit_rate
#   • total_cost

# Also include:
#   • grand_total_cost

# ----------------------------------------
# 🧾 OUTPUT RULES

# - Output MUST be valid JSON
# - All numeric values MUST be ≥ 0
# - Do NOT include negative values

# ----------------------------------------
# 📊 FINAL OUTPUT ORDER

# 1. Elements
# 2. "grand_total_cost"
# 3. "remarks"
# 4. "confidence_score"

# CRITICAL FIXES FOR YOUR CURRENT ISSUE:

# 1. When you see [object Object], treat as INVALID → cost 0 → remark

# 2. When units are mixed (sqft input but metric output):
#    - Convert 2500 sqft → 232 sqm
#    - Use 232 sqm for estimation

# 3. Duct estimation formula (when length missing):
#    length_m = floor_area_m2 × 0.4
#    For 232 sqm → 93 meters total duct length
#    Split 50% to 10x6, 50% to 12x6 (if both rates exist)

# 4. Diffuser estimation:
#    quantity = floor_area_m2 ÷ 10 = 23 diffusers (not 25)

# 5. If elbow rate exists but quantity missing:
#    quantity = diffuser_quantity × 0.8 (typical ratio)

# 6. Grand total = sum of all valid element costs only

# 7. NEVER include invalid items in grand total

# 8. Confidence score for your image = 0.55 (not 0.66) due to:
#    - Unit mismatch
#    - [object Object] in ducts
#    - Missing duct dimensions

# ⚠️ CONTROLLED DISTRIBUTION RULE (ENGINEERING-BASED)

# - If multiple material types exist (e.g., duct_10x6 and duct_12x6)
# - AND no explicit distribution is provided in the input:

# 👉 Distribution MAY be estimated using general engineering practice

# GUIDELINES:
# - Larger sizes → main trunk sections
# - Smaller sizes → branch or terminal sections
# - Total quantity MUST remain conserved (no duplication)

# IMPORTANT:
# - Distribution must be reasonable (not random)
# - Avoid extreme or unrealistic splits
# - Do NOT duplicate total quantities across materials

# TRANSPARENCY RULE:
# - Any assumed distribution MUST be clearly mentioned in remarks

# EXAMPLE REMARK:
# "Estimated duct distribution based on typical trunk and branch layout"

# ❌ DO NOT:
# - Duplicate full quantity for each material
# - Apply arbitrary ratios without engineering logic
# - Hide assumptions from output
# ----------------------------------------
# 🔗 FIELD MAPPING RULE (CRITICAL)

# - Map input fields correctly:

# 1. If "*_meters" exists:
#    → treat as quantity (unit = meter)

#    Example:
#    cable_2x2_5_meters = 450
#    → quantity = 450
#    → unit = "meter"

# 2. If "quantity_data" exists:
#    → use directly as quantity

# 3. NEVER leave quantity empty if value exists in input

# ----------------------------------------
# 📦 MATERIAL-LEVEL OUTPUT RULE (IMPORTANT FIX)

# - DO NOT group outputs (no "CABLES", "OUTLETS")

# - Convert ALL materials into flat list:

# Each item MUST be in output 
# ----------------------------------------
# 🚫 REMOVE WRONG LOGIC

# - DO NOT force unit conversion unless explicitly required
# - DO NOT assume mismatch unless clearly present
# ----------------------------------------
# 🧾 REMARKS RULE (ENFORCED)

# - If ANY invalid data exists:
#   → MUST mention it

# - Format:
#   "Issue; short correction suggestion"

# - Max 12 words

# Example:
# "Invalid duct size; check and correct input size"

# ----------------------------------------
# 📈 CONFIDENCE SCORE

# - Float between 0 and 1

# - If invalid data exists:
#   → MUST reduce confidence

# ----------------------------------------
# 🚫 STRICT CONSTRAINTS

# - ❌ Do NOT hallucinate
# - ❌ Do NOT introduce new elements
# - ❌ Do NOT treat all duct sizes as valid
# - ❌ Do NOT calculate cost using invalid rates

# -❌do not  Assume full floor area coverage
# -❌ Explain how formulas were applied
# -❌ Add generic engineering reasoning
# - AVOID UNIT MISMATCH 

# ----------------------------------------
# 🎯 FINAL INSTRUCTION

# Think like a cost engineer.
# Works commonly for all inputs and uses floor area dynamically
# If invalid data exists:
# → DO NOT calculate cost for that item
# → MUST reflect it in remarks

# Keep remarks minimal, accurate, and non-assumptive.
# Only reflect what was necessary — nothing extra.
# Return ONLY valid JSON.
# """

# # ================================================================
# # CLEAN OUTPUT FUNCTION
# # ================================================================
# def clean_output(text: str) -> str:
#     text = text.strip()

#     if text.startswith("```"):
#         parts = text.split("```")
#         text = parts[1]

#         if text.startswith("json"):
#             text = text[4:]

#     return text.strip()

# # ================================================================
# # CORE BOQ GENERATION FUNCTION
# # ================================================================
# def generate_boq(input_json: dict) -> dict:

#     user_prompt = f"""
# Analyze the following MEP input and generate BOQ JSON.

# INPUT:
# {json.dumps(input_json, indent=2)}
# """

#     try:
#         response = client.chat.completions.create(
#             model="gpt-5-mini",
#             messages=[
#                 {"role": "system", "content": SYSTEM_PROMPT},
#                 {"role": "user", "content": user_prompt}
#             ]
#         )

#         raw = response.choices[0].message.content
#         cleaned = clean_output(raw)

#         return json.loads(cleaned)

#     except Exception as e:
#         return {
#             "error": str(e),
#             "raw_output": raw if 'raw' in locals() else None
#         }

# # ================================================================
# # ROUTES
# # ================================================================
# @app.route("/")
# def index():
#     return render_template("index.html")


# @app.route("/boq", methods=["POST"])
# def boq():

#     if "file" not in request.files:
#         return jsonify({"error": "Upload a JSON file"}), 400

#     file = request.files["file"]

#     if not file.filename.endswith(".json"):
#         return jsonify({"error": "Only JSON allowed"}), 400

#     try:
#         data_list = json.load(file)
#     except Exception as e:
#         return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

#     if isinstance(data_list, dict):
#         data_list = [data_list]

#     results = []
#     errors = []

#     for i, input_json in enumerate(data_list):
#         try:
#             output = generate_boq(input_json)

#             results.append({
#                 "index": i + 1,
#                 "input": input_json,
#                 "output": output
#             })

#         except Exception as e:
#             errors.append({
#                 "index": i + 1,
#                 "error": str(e)
#             })

#     return jsonify({
#         "total": len(data_list),
#         "success": len(results),
#         "failed": len(errors),
#         "results": results,
#         "errors": errors
#     })


# @app.route("/health")
# def health():
#     return jsonify({
#         "status": "ok",
#         "model": "gpt-5-mini"
#     })

# # ================================================================
# # RUN SERVER
# # ================================================================
# if __name__ == "__main__":
#     app.run(debug=True, port=5000)





from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import os
from dotenv import load_dotenv
from openai import OpenAI

# ================================================================
# ENVIRONMENT SETUP
# ================================================================
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("❌ OPENAI_API_KEY not found")

# ================================================================
# FLASK APP INITIALIZATION
# ================================================================
app = Flask(__name__)
CORS(app)

# ================================================================
# OPENAI CLIENT
# ================================================================
client = OpenAI(api_key=api_key)

# ================================================================
# SYSTEM PROMPT (UNCHANGED LOGIC)
# ================================================================
SYSTEM_PROMPT = """
You are an advanced MEP BOQ (Bill of Quantities) estimation system.

Your objective is to analyze structured input data and generate a BOQ by extracting elements, estimating quantities, and calculating costs in a controlled, engineering-accurate, and market-realistic manner.

----------------------------------------
INPUT DATA:
{{input_json}}
----------------------------------------

🔍 INPUT UNDERSTANDING

- Analyze input structure carefully.
- Identify:
  • Materials (with size/specification)
  • Quantities / counts / structure
  • Material rates (if available)

IMPORTANT:
- Use ONLY input materials
- Do NOT add new materials
- Do NOT remove input materials

----------------------------------------
🧠 MATERIAL PRESERVATION

- Every input material MUST appear in output
- Preserve:
  • name
  • size

- If value is NULL:
  → keep NULL
  → do NOT modify
  → do NOT penalize confidence

----------------------------------------
📐 QUANTITY ESTIMATION

- Use input structure (branches, sections, counts)
- If quantity missing → estimate minimally
- Do NOT assume full floor coverage

----------------------------------------
🔢 QUANTITY RULE

- Integer only
- ≥ 0.5 → round up
- < 0.5 → round down

----------------------------------------
💰 UNIT RATE HANDLING (FIXED — REALISTIC PRICING)

IF material_rates exist:
→ use directly

IF material_rates NOT provided:

👉 Estimate unit_rate using REALISTIC MARKET RANGES

----------------------------------------
📊 PRICE ESTIMATION GUIDELINES (CRITICAL)

⚠️ ALWAYS use realistic cost scale

DUCTS (per meter):
- Small (4–6 inch) → ₹300 – ₹500
- Medium (8–10 inch) → ₹500 – ₹800
- Large (12–16 inch) → ₹800 – ₹1500+

FITTINGS / ELBOWS (per piece):
- ₹150 – ₹400 depending on size

DIFFUSERS:
- ₹500 – ₹1200 per unit

----------------------------------------
📐 SIZE-BASED SCALING RULE

- Extract size (diameter or width)
- Increase cost proportionally with size

Example:
- 6 inch → lower range
- 10 inch → mid range
- 14 inch → higher range

----------------------------------------
🚫 INVALID PRICING RULE

- DO NOT assign unrealistic values like:
  ❌ ₹10
  ❌ ₹20
  ❌ ₹50

- If estimated price is too low:
  → adjust to minimum realistic threshold

----------------------------------------
💰 COST CALCULATION

total_cost = quantity × unit_rate

RULE:
- If quantity > 0 AND unit_rate > 0:
  → MUST calculate cost

----------------------------------------
⚠️ NULL HANDLING

- Preserve NULL values
- Do NOT reduce confidence due to NULL

----------------------------------------
⚠️ VALIDATION RULE

- Only mark invalid if:
  • quantity AND rate both unavailable

----------------------------------------
📊 OUTPUT

- Include ONLY input materials

Each item:
  • name
  • size
  • quantity
  • unit_rate
  • total_cost

Also:
  • grand_total_cost

----------------------------------------
🧾 REMARKS

- Max 12 words
- Example:
  "Unit rates estimated using market-based size scaling"

----------------------------------------
📈 CONFIDENCE SCORE

- Do NOT reduce for NULL
- Reduce only if heavy estimation used

----------------------------------------
🚫 STRICT RULES

- ❌ No new materials
- ❌ No removal of input materials
- ❌ No unrealistic pricing
- ❌ No zero cost when estimation possible

----------------------------------------
🎯 FINAL INSTRUCTION

Think like a real cost engineer.

- Use realistic market pricing
- Scale cost with size
- Preserve input integrity

Return ONLY valid JSON.
"""
# (No change — keep your existing prompt content exactly)

# ================================================================
# CLEAN OUTPUT FUNCTION
# ================================================================
def clean_output(text: str) -> str:
    """
    Cleans LLM output by removing markdown wrappers if present
    """
    text = text.strip()

    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1]

        if text.startswith("json"):
            text = text[4:]

    return text.strip()


# ================================================================
# CORE BOQ GENERATION FUNCTION
# ================================================================
def generate_boq(input_json: dict) -> dict:
    """
    Calls LLM and returns structured BOQ output
    """

    user_prompt = f"""
Analyze the following MEP input and generate BOQ JSON.

INPUT:
{json.dumps(input_json, indent=2)}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
        )

        raw_output = response.choices[0].message.content
        cleaned_output = clean_output(raw_output)

        return json.loads(cleaned_output)

    except Exception as e:
        return {
            "error": str(e),
            "raw_output": raw_output if "raw_output" in locals() else None
        }


# ================================================================
# ROUTES
# ================================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/boq", methods=["POST"])
def boq():
    """
    Handles file upload and processes BOQ generation
    """

    # ---------------------------
    # FILE VALIDATION
    # ---------------------------
    if "file" not in request.files:
        return jsonify({"error": "Upload a JSON file"}), 400

    file = request.files["file"]

    if not file.filename.endswith(".json"):
        return jsonify({"error": "Only JSON files are allowed"}), 400

    # ---------------------------
    # LOAD JSON
    # ---------------------------
    try:
        data = json.load(file)
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

    # Normalize to list
    if isinstance(data, dict):
        data = [data]

    results = []
    errors = []

    # ---------------------------
    # PROCESS EACH INPUT
    # ---------------------------
    for idx, input_json in enumerate(data):
        try:
            output = generate_boq(input_json)

            results.append({
                "index": idx + 1,
                "input": input_json,
                "output": output
            })

        except Exception as e:
            errors.append({
                "index": idx + 1,
                "error": str(e)
            })

    # ---------------------------
    # FINAL RESPONSE
    # ---------------------------
    return jsonify({
        "total": len(data),
        "success": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors
    })


@app.route("/health")
def health():
    """
    Health check endpoint
    """
    return jsonify({
        "status": "ok",
        "model": "gpt-5-mini"
    })


# ================================================================
# RUN SERVER
# ================================================================
if __name__ == "__main__":
    app.run(debug=True, port=5000)