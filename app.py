import sys
import os
import threading
import time
import pandas as pd
from flask import Flask, send_from_directory, request, jsonify
from werkzeug.utils import secure_filename
from playwright.sync_api import sync_playwright
import shutil # این را در بالای فایل ایمپورت کنید

# --- ایمپورت ماژول اتوماسیون ---
from browser.browser import run_browser_task

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

# چاپ مسیر ذخیره‌سازی برای اطمینان
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
        print(f"--> File Saved: {full_path}") # دیباگ
        
        return jsonify({"message": "OK", "filename": filename}), 200

# --- (بخش گمشده) لیست کردن فایل‌ها ---
@app.route("/files/<folder>", methods=['GET'])
def list_files(folder):
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
    if not os.path.exists(folder_path):
        return jsonify([]) # اگر پوشه نبود، لیست خالی برگردان
    
    # لیست کردن فایل‌ها و حذف فایل‌های سیستمی (مثل .DS_Store)
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

@app.route("/run-workflow", methods=['POST'])
def run_workflow():
    data = request.json
    excel_full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'users', data.get('excelFile'))
    workflow_full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'workflows', data.get('workflowFile'))
    
    try:
        output = run_browser_task(excel_full_path, workflow_full_path)
        return jsonify({"status": "success", "output": output}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -----------------------------------
# --- توابع اجرای برنامه (GUI) ---
# -----------------------------------

def run_flask_server():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)

def start_gui():
    """اجرای رابط کاربری با سایز اجباری"""
    print("Initializing GUI...")
    
    # مسیر پروفایل
    user_data_dir = os.path.join(get_base_path(), "browser_profile")
    
    # عرض و ارتفاع دلخواه
    WIDTH = 1200
    HEIGHT = 700

    try:
        with sync_playwright() as p:
            print("Launching App Mode...")
            
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                viewport=None, # اجازه میدهیم پنجره توسط سیستم عامل مدیریت شود
                args=[
                    "--app=http://127.0.0.1:5000",
                    # این آرگومان فقط بار اول کار میکند، اما نوشتنش ضرر ندارد
                    f"--window-size={WIDTH},{HEIGHT}",
                    "--no-first-run",
                    "--disable-infobars"
                ],
                ignore_default_args=["--enable-automation"]
            )
            
            page = context.pages[0]
            
            # --- بخش جدید: تغییر سایز اجباری ---
            # چون کروم ممکن است سایز قبلی را لود کرده باشد، ما با زور آن را تغییر میدهیم!
            try:
                # اتصال به پروتکل سطح پایین کروم
                session = context.new_cdp_session(page)
                
                # گرفتن شناسه پنجره فعلی
                window_info = session.send("Browser.getWindowForTarget")
                window_id = window_info["windowId"]
                
                # اعمال سایز جدید
                session.send("Browser.setWindowBounds", {
                    "windowId": window_id,
                    "bounds": {
                        "width": WIDTH,
                        "height": HEIGHT,
                        "windowState": "normal" # اطمینان از اینکه مینییمایز یا ماکسیمایز نیست
                    }
                })
                print(f"Window resized to {WIDTH}x{HEIGHT}")
            except Exception as resize_err:
                print(f"Could not force resize: {resize_err}")
            # -----------------------------------

            print("Application Started.")
            
            while True:
                try:
                    if page.is_closed():
                        break
                    time.sleep(1)
                except:
                    break
            
            context.close()
            
    except Exception as e:
        print(f"Failed to launch GUI: {e}")
    finally:
        print("Exiting application...")
        os._exit(0)



if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask_server)
    flask_thread.daemon = True
    flask_thread.start()
    time.sleep(1.5)
    start_gui()
