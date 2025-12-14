import sys
import os
import threading
import time
import pandas as pd
from flask import Flask, send_from_directory, request, jsonify
from werkzeug.utils import secure_filename
from playwright.sync_api import sync_playwright
import shutil

# --- ایمپورت ماژول اتوماسیون ---
# import from browser.browser import run_browser_task
# (فرض بر این است که این ماژول وجود دارد)

def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(base_path, "pw-browsers")
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- تنظیمات فلاسک ---
app = Flask(__name__, static_folder=get_resource_path("static"))
BASE_DIR = get_base_path()
BASE_UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
app.config['UPLOAD_FOLDER'] = BASE_UPLOAD_FOLDER
print(f"--> Uploads will be saved to: {BASE_UPLOAD_FOLDER}")
os.makedirs(os.path.join(BASE_UPLOAD_FOLDER, 'users'), exist_ok=True)
os.makedirs(os.path.join(BASE_UPLOAD_FOLDER, 'workflows'), exist_ok=True)

# -----------------------------------
# --- روت‌های فلاسک (Routes) ---
# -----------------------------------

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

@app.route("/upload/<folder>", methods=['POST'])
def upload_file(folder):
    if 'file' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"error": "No selected file"}), 400
    if file:
        filename = secure_filename(file.filename)
        folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
        os.makedirs(folder_path, exist_ok=True)
        full_path = os.path.join(folder_path, filename)
        file.save(full_path)
        print(f"--> File Saved: {full_path}")
        return jsonify({"message": "OK", "filename": filename}), 200

@app.route("/files/<folder>", methods=['GET'])
def list_files(folder):
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
    if not os.path.exists(folder_path):
        return jsonify([])
    files = [f for f in os.listdir(folder_path) if not f.startswith('.')]
    return jsonify(files), 200

@app.route("/view-excel/<filename>", methods=['GET'])
def view_excel(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'users', filename)
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found on disk"}), 404
        df = pd.read_excel(file_path).fillna("")
        return jsonify({"headers": df.columns.tolist(), "rows": df.values.tolist()}), 200
    except Exception as e:
        print(f"Error reading excel: {e}")
        return jsonify({"error": str(e)}), 500

# --- کد جدید برای حذف فایل ---
@app.route("/delete/<folder>/<filename>", methods=['DELETE'])
def delete_file(folder, filename):
    # برای امنیت، بررسی می‌کنیم که فقط از پوشه‌های مجاز حذف انجام شود
    if folder not in ['users', 'workflows']:
        return jsonify({"error": "Invalid folder specified"}), 400
    
    try:
        # استفاده از secure_filename برای جلوگیری از حملات Directory Traversal
        secure_name = secure_filename(filename)
        if secure_name != filename:
            return jsonify({"error": "Invalid filename"}), 400

        folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
        file_path = os.path.join(folder_path, secure_name)

        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"--> File Deleted: {file_path}")
            return jsonify({"message": "File deleted successfully"}), 200
        else:
            print(f"--> Delete failed. File not found: {file_path}")
            return jsonify({"error": "File not found"}), 404

    except Exception as e:
        print(f"Error deleting file: {e}")
        return jsonify({"error": str(e)}), 500
# --- پایان کد جدید ---

@app.route("/run-workflow", methods=['POST'])
def run_workflow():
    data = request.json
    excel_full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'users', data.get('excelFile'))
    workflow_full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'workflows', data.get('workflowFile'))
    try:
        # فرض بر این است که تابع run_browser_task در دسترس است
        # output = run_browser_task(excel_full_path, workflow_full_path)
        output = "Workflow executed successfully (mocked)."
        return jsonify({"status": "success", "output": output}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -----------------------------------
# --- توابع اجرای برنامه (GUI) ---
# -----------------------------------
def run_flask_server():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)

def start_gui():
    """
    اجرای رابط کاربری گرافیکی (GUI) با راه‌حل Polling برای تشخیص و اعمال تغییر سایز.
    این روش در محیط‌هایی مانند Ubuntu/Wayland به درستی کار می‌کند.
    """
    print("Initializing GUI...")
    user_data_dir = os.path.join(get_base_path(), "browser_profile")
    try:
        with sync_playwright() as p:
            print("Launching App Mode...")
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                viewport=None,  # اجازه می‌دهیم پنجره آزادانه تغییر سایز کند
                args=[
                    "--no-first-run",
                    "--disable-infobars"
                ],
                ignore_default_args=["--enable-automation"]
            )
            page = context.pages[0]
            page.goto('http://127.0.0.1:5000')
            print("Application Started.")
            
            # --- شروع کد جدید برای تشخیص و اعمال تغییر سایز ---
            # آخرین سایز ثبت شده را None می‌گذاریم تا در اولین اجرا، سایز تنظیم شود
            last_size = None
            print("Starting resize polling loop...")
            while not page.is_closed():
                try:
                    # 1. از طریق جاوا اسکریپت، ابعاد فعلی viewport را از صفحه می‌خوانیم
                    current_size = page.evaluate("() => ({ width: window.innerWidth, height: window.innerHeight })")
                    
                    # 2. اگر سایز تغییر کرده بود...
                    if current_size != last_size:
                        print(f"--> Window resized to: {current_size}")
                        # 3. (مهم‌ترین بخش) سایز جدید را به صورت دستوری به viewport صفحه اعمال می‌کنیم.
                        # این کار به Playwright و موتور رندر صفحه اطلاع می‌دهد که باید خود را با این سایز جدید تطبیق دهند.
                        page.set_viewport_size(current_size)
                        # 4. سایز جدید را ذخیره می‌کنیم تا در تکرار بعدی مقایسه شود
                        last_size = current_size
                    
                    # هر 0.3 ثانیه یک بار چک می‌کنیم تا به CPU فشار نیاید
                    time.sleep(0.3)
                except Exception:
                    # اگر در حین کار پنجره بسته شد، از حلقه خارج شو
                    print("Page closed, exiting polling loop.")
                    break
            # --- پایان کد جدید ---

            print("Browser window closed by user.")
            context.close()
    except Exception as e:
        print(f"Failed to launch GUI: {e}")
    finally:
        print("Exiting application...")
        os._exit(0)

# ... (بقیه کد شما برای اجرای flask و start_gui) ...
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask_server)
    flask_thread.daemon = True
    flask_thread.start()
    time.sleep(1.5)
    start_gui()
