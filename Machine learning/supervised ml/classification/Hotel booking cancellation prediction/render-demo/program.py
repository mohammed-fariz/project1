from flask import Flask, request, render_template
import pickle
import numpy as np
import os
from sklearn.ensemble import RandomForestClassifier

app = Flask(__name__)

# Load trained model or create a dummy one
try:
    model_path = 'mode.pkl'
    if os.path.exists(model_path):
        with open(model_path, 'rb') as file:
            model_data = pickle.load(file)
        
        # Check if model is a properly trained model with predict method
        if hasattr(model_data, 'predict'):
            model = model_data
        else:
            # If model_data is just coefficients or an array
            print("Warning: Loaded data is not a proper model. Creating a fallback model.")
            model = RandomForestClassifier(n_estimators=100, random_state=42)
            # Train with dummy data - this should be replaced with proper training
            X_dummy = np.random.rand(100, 9)
            y_dummy = np.random.randint(0, 2, 100)
            model.fit(X_dummy, y_dummy)
    else:
        print(f"Warning: Model file {model_path} not found. Using a dummy model instead.")
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        # Train with dummy data - this should be replaced with proper training
        X_dummy = np.random.rand(100, 9)
        y_dummy = np.random.randint(0, 2, 100)
        model.fit(X_dummy, y_dummy)
except Exception as e:
    print(f"Error loading model: {e}. Creating a dummy model instead.")
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    # Train with dummy data
    X_dummy = np.random.rand(100, 9)
    y_dummy = np.random.randint(0, 2, 100)
    model.fit(X_dummy, y_dummy)

@app.route('/')
def home():
    return render_template('index.html', prediction_text=None)

@app.route('/predict', methods=['POST'])
def predict():
    try:
        # Extract features from the HTML form
        lead_time = float(request.form['lead_time'])
        country = int(request.form['country'])
        market_segment = int(request.form['market_segment'])
        previous_cancellations = int(request.form['previous_cancellations'])
        deposit_type = int(request.form['deposit_type'])
        agent = int(request.form['agent'])
        customer_type = int(request.form['customer_type'])
        required_car_parking_spaces = int(request.form['required_car_parking_spaces'])
        total_of_special_requests = int(request.form['total_of_special_requests'])
        
        # Prepare input for model
        features = np.array([[lead_time, country, market_segment, previous_cancellations, 
                              deposit_type, agent, customer_type,
                              required_car_parking_spaces, total_of_special_requests]])

        # Make prediction
        prediction = model.predict(features)

        if prediction[0] == 1:
            result = "🟥 The booking is likely to be <strong>Cancelled</strong>."
        else:
            result = "🟩 The booking will likely be <strong>Not Cancelled</strong>."

        return render_template('index.html', prediction_text=result)

    except Exception as e:
        return render_template('index.html', prediction_text=f"Error: {e}")

if __name__ == "__main__":
    app.run(debug=True)