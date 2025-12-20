from flask import Flask, request, jsonify, render_template
import joblib
import pandas as pd

# -------------------------------
# Initialize Flask app
# -------------------------------
app = Flask(__name__)

# -------------------------------
# Load trained model
# -------------------------------
model_path = r"C:\Users\USER\Desktop\project1\supervised ml\customer lifetime value prediciton\clv_model.pkl"
model = joblib.load(model_path)

# -------------------------------
# Define expected features
# -------------------------------
features =  [
    'Unit_Price',
    'Discount_Amount',
    'Quantity',
    
    'Payment_Method',
    'Product_Category'
]

# -------------------------------
# Home Route
# -------------------------------
@app.route('/')
def home():
    return render_template('index.html')

# -------------------------------
# Prediction Route
# -------------------------------
@app.route('/predict', methods=['POST'])
def predict():
    try:
        # Collect form input values in the correct feature order
        input_values = []
        for f in features:
            val = request.form.get(f, 0)
            input_values.append(float(val))

        # Convert to DataFrame
        input_df = pd.DataFrame([input_values], columns=features)

        # Make prediction
        prediction = model.predict(input_df)[0]

        return render_template(
            'index.html',
            prediction_text=f"Predicted Total CLV: {prediction:.2f}"
        )

    except Exception as e:
        return jsonify({"error": str(e)})

# -------------------------------
# Run Flask App
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)
