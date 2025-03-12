from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import os
import cv2
import pytesseract
import re
from datetime import datetime

# Setup
app = Flask(__name__)
IMAGE_DIR = "img"
DB_PATH = "receipts.db"
COUNTER_FILE = "counter.txt"

os.makedirs(IMAGE_DIR, exist_ok=True)

if not os.path.exists(COUNTER_FILE):
    with open(COUNTER_FILE, 'w') as f:
        f.write('0')

def preprocess_image(image_path):
    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    image = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, image = cv2.threshold(image, 150, 255, cv2.THRESH_BINARY)
    return image

def extract_total_from_receipt(image_path):
    image = preprocess_image(image_path)
    text = pytesseract.image_to_string(image, lang='eng+tha')
    
    total = None
    for line in text.splitlines():
        if "NET-TOTAL:" in line:
            try:
                total = line.split("NET-TOTAL:")[-1].strip()
                total = float(re.sub(r'[^\d.]', '', total))
                break
            except ValueError:
                pass
    
    if total is None:
        # Fallback
        numbers = [float(re.sub(r'[^\d.]', '', num))
                   for num in re.findall(r'\d[\d,]*\.?\d*', text)]
        if numbers:
            total = max(numbers)
    
    if total is None:
        raise ValueError("No numeric value found in the receipt.")
    return round(total, 2)

#Database
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total REAL NOT NULL,
                timestamp TEXT NOT NULL,
                category TEXT DEFAULT 'Uncategorized'
            )
        """)
def calculate_total_expense():
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute("SELECT SUM(total) FROM receipts").fetchone()
        print("Total expense calculation result:", result)
        return result[0] if result and result[0] is not None else 0.0



def insert_receipt(total, timestamp):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO receipts (total, timestamp) VALUES (?, ?)", (total, timestamp))
    return

def fetch_receipts():
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT id, total, timestamp, category FROM receipts").fetchall()

def delete_receipt(receipt_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
    return

def update_receipt(receipt_id, total):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE receipts SET total = ? WHERE id = ?", (total, receipt_id))
    return

# Flask
@app.route("/")
def index():
    receipts = fetch_receipts()
    total_expense = calculate_total_expense()
    return render_template("index.html", receipts=receipts, total_expense=total_expense)



@app.route("/add", methods=["POST"])
def add_receipt():
    total = request.form.get("total")
    timestamp = request.form.get("timestamp")
    category = request.form.get("category")

    try:
        total = float(total)  # Ensure valid float
        timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M").strftime("%Y-%m-%d %H:%M:%S")
        category = category or "Uncategorized"  # Fallback category if not provided

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO receipts (total, timestamp, category)
                VALUES (?, ?, ?)
            """, (total, timestamp, category))
    except ValueError as e:
        print(f"Error adding receipt: {e}")

    return redirect(url_for("index"))



@app.route("/edit_category/<int:receipt_id>", methods=["POST"])
def edit_category(receipt_id):
    new_category = request.form.get("category")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE receipts SET category = ? WHERE id = ?", (new_category, receipt_id))
    return redirect(url_for("index"))

@app.route("/manual", methods=["POST"])
def add_manual_receipt():
    total = request.form.get("total")
    timestamp = request.form.get("timestamp")
    category = request.form.get("category") 

    try:
        total = float(total)
        timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M").strftime("%Y-%m-%d %H:%M:%S")
        
        #database include category
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO receipts (total, timestamp, category)
                VALUES (?, ?, ?)
            """, (total, timestamp, category or "Uncategorized"))  # Fallback to "Uncategorized"

        print(f"Added receipt: Total={total}, Timestamp={timestamp}, Category={category}")
    except ValueError as e:
        print(f"Error adding receipt: {e}")

    return redirect(url_for("index"))


@app.route("/capture", methods=["GET"])
def capture():
    # Webcam
    counter = int(open(COUNTER_FILE).read())
    image_name = f"{counter + 1}.png"
    image_path = os.path.join(IMAGE_DIR, image_name)

    cap = cv2.VideoCapture(0)
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to capture frame.")
            break

        cv2.imshow("Capture Receipt", frame)
        key = cv2.waitKey(1)
        if key == 27:  #esc exit
            break
        elif key == 32:  #spacebar capture
            cv2.imwrite(image_path, frame)
            break

    cap.release()
    cv2.destroyAllWindows()

    #update counter
    with open(COUNTER_FILE, 'w') as f:
        f.write(str(counter + 1))

    #ocr
    try:
        total = extract_total_from_receipt(image_path)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        insert_receipt(total, timestamp)
    except ValueError as e:
        print(f"Error processing receipt: {e}")

    return redirect(url_for("index"))

@app.route("/delete/<int:receipt_id>")
def delete(receipt_id):
    delete_receipt(receipt_id)
    return redirect(url_for("index"))

@app.route("/edit/<int:receipt_id>", methods=["GET", "POST"])
def edit(receipt_id):
    if request.method == "POST":
        new_total = request.form.get("total")
        try:
            new_total = float(new_total)
            update_receipt(receipt_id, new_total)
        except ValueError:
            print("Invalid total value.")
        return redirect(url_for("index"))
    
    #edit form
    receipt = fetch_receipts()[receipt_id - 1]
    return render_template("edit_receipt.html", receipt=receipt)

# Main
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
