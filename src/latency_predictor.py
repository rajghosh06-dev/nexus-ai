import pandas as pd
import numpy as np
import os
import pickle
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime

# --- Configuration & Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data", "raw_pings.csv")
MODEL_DIR = os.path.join(BASE_DIR, "models")
MODEL_FILE = os.path.join(MODEL_DIR, "latency_model.pkl")


def train_model():
    """Reads the CSV, trains a regression model, and saves it."""
    print("[*] Loading raw ping data...")

    if not os.path.exists(DATA_FILE):
        print("[-] Error: Data file not found. Let the tracker run first.")
        return

    # Load data using Pandas
    df = pd.read_csv(DATA_FILE)

    # FIX: Strip any accidental leading/trailing spaces from the column headers
    df.columns = df.columns.str.strip()

    # Check if the column exists now
    if 'latency_ms' not in df.columns:
        print(f"[-] Error: 'latency_ms' column missing. Available columns: {list(df.columns)}")
        print("[-] Try deleting the 'data/raw_pings.csv' file and restarting the tracker script.")
        return

    # Clean Data: Remove packet loss (-1.0) so it doesn't skew standard latency math
    df = df[df['latency_ms'] > 0].copy()

    if len(df) < 10:
        print(f"[-] Not enough data to train. Current row count: {len(df)}. Need at least 10.")
        return

    print(f"[*] Processing {len(df)} rows of data...")

    # --- Feature Engineering ---
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['hour'] = df['timestamp'].dt.hour
    df['minute'] = df['timestamp'].dt.minute

    # Convert server names to numbers
    df['server_code'] = df['server_name'].astype('category').cat.codes

    # X (Inputs) and y (Output)
    X = df[['hour', 'minute', 'server_code']]
    y = df['latency_ms']

    # --- Model Training ---
    print("[*] Training Random Forest Regression Model...")
    model = RandomForestRegressor(n_estimators=50, random_state=42)
    model.fit(X, y)

    # --- Save Model ---
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(MODEL_FILE, 'wb') as file:
        pickle.dump(model, file)

    print(f"[*] Success! Model trained and saved to {MODEL_FILE}")


def predict_latency(hour, minute, server_code=0):
    """Loads the model and predicts latency for a specific time."""
    if not os.path.exists(MODEL_FILE):
        return "Model not trained yet."

    with open(MODEL_FILE, 'rb') as file:
        model = pickle.load(file)

    # Format input to match training data
    input_data = pd.DataFrame([[hour, minute, server_code]], columns=['hour', 'minute', 'server_code'])
    prediction = model.predict(input_data)[0]

    return round(prediction, 2)


if __name__ == "__main__":
    # Test the training pipeline
    train_model()

    # Run a quick test prediction for the current time
    now = datetime.now()
    test_pred = predict_latency(now.hour, now.minute, server_code=0)
    print(f"[*] Test Prediction -> Estimated Latency right now: {test_pred} ms")