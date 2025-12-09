import sys
import os
import pandas as pd
from flask import Flask, send_from_directory, request, jsonify
from werkzeug.utils import secure_filename
from playwright.sync_api import sync_playwright



# اگر برنامه به صورت فایل اجرایی (Frozen) اجرا شود
if getattr(sys, 'frozen', False):
    # مسیر پوشه موقت که فایل‌ها آنجا باز شده‌اند
    bundle_dir = sys._MEIPASS
    
    # به Playwright می‌گوییم مرورگرها را در پوشه pw-browsers که ما ساختیم پیدا کند
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(bundle_dir, "pw-browsers")
    
# --- (مهم) ایمپورت کردن ماژول مرورگر ---
# فرض بر این است که فایل در پوشه browser/browser.py است
# و یک فایل خالی __init__.py در پوشه browser وجود دارد.
from browser.browser import run_browser_task

def get_base_path():
    """
    مسیر اجرای برنامه را برمی‌گرداند.
    در حالت فایل اجرایی: مسیری که فایل exe قرار دارد.
    در حالت پایتون معمولی: مسیری که فایل py قرار دارد.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    """
    مسیر فایل‌های داخلی (مثل static) را مدیریت می‌کند.
    در حالت فایل اجرایی، این فایل‌ها در پوشه موقت (MEIPASS) هستند.
    """
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# تنظیم مسیر استاتیک با استفاده از تابع resource_path
app = Flask(__name__, static_folder=get_resource_path("static"))

# تنظیم مسیر آپلودها (کنار فایل اجرایی ساخته شود)
BASE_DIR = get_base_path()
BASE_UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
app.config['UPLOAD_FOLDER'] = BASE_UPLOAD_FOLDER

# ایجاد فولدرهای پیش‌فرض
os.makedirs(os.path.join(BASE_UPLOAD_FOLDER, 'users'), exist_ok=True)
os.makedirs(os.path.join(BASE_UPLOAD_FOLDER, 'workflows'), exist_ok=True)

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

# --- مدیریت فایل‌ها ---
@app.route("/upload/<folder>", methods=['POST'])
def upload_file(folder):
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file:
        filename = secure_filename(file.filename)
        folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
        os.makedirs(folder_path, exist_ok=True)
        file.save(os.path.join(folder_path, filename))
        return jsonify({"message": "File uploaded successfully", "filename": filename}), 200

@app.route("/files/<folder>", methods=['GET'])
def list_files(folder):
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
    if not os.path.isdir(folder_path):
        os.makedirs(folder_path, exist_ok=True)
        return jsonify([]), 200
    files = os.listdir(folder_path)
    # حذف فایل‌های مخفی
    files = [f for f in files if not f.startswith('.')]
    return jsonify(files), 200

@app.route("/delete/<folder>/<filename>", methods=['DELETE'])
def delete_file(folder, filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], folder, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return jsonify({"message": "File deleted"}), 200
    return jsonify({"error": "File not found"}), 404

# --- نمایش محتوای اکسل ---
@app.route("/view-excel/<filename>", methods=['GET'])
def view_excel(filename):
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], 'users')
    file_path = os.path.join(folder_path, filename)
    
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    
    try:
        df = pd.read_excel(file_path)
        df = df.fillna("")
        data = {
            "headers": df.columns.tolist(),
            "rows": df.values.tolist()
        }
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- اجرای ورک‌فلو (اصلاح شده) ---
@app.route("/run-workflow", methods=['POST'])
def run_workflow():
    data = request.json
    excel_filename = data.get('excelFile')
    workflow_filename = data.get('workflowFile')

    if not excel_filename or not workflow_filename:
        return jsonify({"error": "Missing parameters"}), 400

    # ساخت مسیر کامل فایل‌ها برای ارسال به تابع مرورگر
    excel_full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'users', excel_filename)
    workflow_full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'workflows', workflow_filename)

    try:
        # فراخوانی مستقیم تابع (بدون subprocess)
        # نکته: این کار تا پایان اجرای مرورگر، پاسخ‌دهی سرور را نگه‌می‌دارد.
        output = run_browser_task(excel_full_path, workflow_full_path)
        
        return jsonify({"status": "success", "output": output}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # host=0.0.0.0 ممکن است در ویندوز فایروال را حساس کند، برای لوکال 127.0.0.1 امن‌تر است
    app.run(host="127.0.0.1", port=5000, debug=True)
