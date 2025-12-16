import sys
import os
import threading
import time
import json
import pandas as pd
import mimetypes

from flask import Flask, send_from_directory, request, jsonify
from werkzeug.utils import secure_filename
from playwright.sync_api import sync_playwright

# -----------------------------------
# --- تنظیمات مسیردهی هوشمند ---
# -----------------------------------

def get_base_path():
    """
    مسیر ریشه پروژه را برمی‌گرداند.
    سازگار با حالت Development و حالت Frozen (exe).
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    base_path = get_base_path()
    return os.path.join(base_path, relative_path)

# --- متغیرهای مسیر ---
BASE_DIR = get_base_path()
BROWSER_DIR = os.path.join(BASE_DIR, 'browser')
STATIC_DIR = get_resource_path("static")
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')

# --- اضافه کردن مسیر browser به پایتون ---
if BROWSER_DIR not in sys.path:
    sys.path.append(BROWSER_DIR)

# --- ایمپورت ماژول‌های اتوماسیون ---
print("--> Loading Automation Modules...")
try:
    # چون BROWSER_DIR در sys.path است، مستقیم نام فایل را می‌زنیم
    from build_exam_file import process_exam
    from appCourser4 import run_course_automation
    print("--> Modules loaded successfully.")
except ImportError as e:
    print("\n" + "!"*50)
    print(f"CRITICAL ERROR: Could not import modules from {BROWSER_DIR}")
    print(f"Error Details: {e}")
    print("Ensure 'build_exam_file.py' and 'appCourser4.py' exist in 'browser' folder.")
    print("!"*50 + "\n")
    sys.exit(1)

# -----------------------------------
# --- تنظیمات فلاسک ---
# -----------------------------------
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

app = Flask(__name__, static_folder=STATIC_DIR)
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR

# تنظیم مسیر مرورگرهای Playwright
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(BROWSER_DIR, "pw-browsers")

os.makedirs(os.path.join(UPLOAD_DIR, 'users'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, 'workflows'), exist_ok=True)

print(f"--> Base Dir:    {BASE_DIR}")
print(f"--> Browser Dir: {BROWSER_DIR}")
print(f"--> Static Dir:  {STATIC_DIR}")
print(f"--> Uploads Dir: {UPLOAD_DIR}")

# -----------------------------------
# --- روت‌های فلاسک ---
# -----------------------------------

@app.route("/")
def index():
    full_path = os.path.join(app.static_folder, "index.html")
    if not os.path.exists(full_path):
        return f"Error: index.html not found at {full_path}", 404
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
        if folder == 'workflows':
            return jsonify({"error": "Workflow uploads are managed by system."}), 403
            
        folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
        os.makedirs(folder_path, exist_ok=True)
        
        full_path = os.path.join(folder_path, filename)
        file.save(full_path)
        print(f"--> File Saved: {full_path}")
        return jsonify({"message": "OK", "filename": filename}), 200

@app.route("/files/<folder>", methods=['GET'])
def list_files(folder):
    if folder == 'workflows':
        try:
            workflow_json_path = os.path.join(BROWSER_DIR, 'workflows.json')
            if not os.path.exists(workflow_json_path):
                return jsonify([]), 200
            
            with open(workflow_json_path, 'r', encoding='utf-8') as f:
                workflows_data = json.load(f)
                workflow_names = [wf.get('name', 'Unnamed') for wf in workflows_data]
                return jsonify(workflow_names), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
    if not os.path.exists(folder_path):
        return jsonify([]), 200
        
    files = [f for f in os.listdir(folder_path) if not f.startswith('.')]
    return jsonify(files), 200

@app.route("/view-excel/<filename>", methods=['GET'])
def view_excel(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'users', filename)
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
            
        df = pd.read_excel(file_path).fillna("")
        return jsonify({"headers": df.columns.tolist(), "rows": df.values.tolist()}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/delete/<folder>/<filename>", methods=['DELETE'])
def delete_file(folder, filename):
    if folder not in ['users', 'workflows']:
        return jsonify({"error": "Invalid folder"}), 400
    try:
        secure_name = secure_filename(filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], folder, secure_name)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"--> File Deleted: {file_path}")
            return jsonify({"message": "Deleted"}), 200
        else:
            return jsonify({"error": "Not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/run-workflow", methods=['POST'])
def run_workflow():
    data = request.json
    selected_excel_file = data.get('excelFile')
    selected_workflow_name = data.get('workflowFile')

    print(f"--> Request: Run '{selected_workflow_name}' with '{selected_excel_file}'")
    total_output = ""

    try:
        # 1. تنظیمات
        workflow_json_path = os.path.join(BROWSER_DIR, 'workflows.json')
        with open(workflow_json_path, 'r', encoding='utf-8') as f:
            workflows_data = json.load(f)
        
        workflow_info = next((item for item in workflows_data if item["name"] == selected_workflow_name), None)
        if not workflow_info:
            return jsonify({"error": "Workflow info not found"}), 404

        # 2. مسیرها
        excel_full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'users', selected_excel_file)
        input_dir = os.path.join(BASE_DIR, workflow_info['exams_step_dir'])
        output_filename = f"{selected_workflow_name}.json"
        output_workflow_path = os.path.join(app.config['UPLOAD_FOLDER'], 'workflows', secure_filename(output_filename))

        # 3. اجرا - Build
        print("--> Step 1: Building Exam File...")
        build_success, build_logs = process_exam(excel_full_path, input_dir, output_workflow_path)
        total_output += f"--- Build Logs ---\n{build_logs}\n"

        if not build_success:
            return jsonify({"error": f"Build Failed.\nLogs:\n{build_logs}"}), 500

        # 4. اجرا - Automation
        print("--> Step 2: Running Automation...")
        run_success, run_logs = run_course_automation(output_workflow_path)
        total_output += f"\n--- Automation Logs ---\n{run_logs}\n"

        if not run_success:
            return jsonify({"error": f"Automation Failed.\nLogs:\n{run_logs}"}), 500

        return jsonify({"status": "success", "output": total_output}), 200

    except Exception as e:
        print(f"--> Exception in run_workflow: {e}")
        return jsonify({"error": str(e)}), 500

# -----------------------------------
# --- GUI Logic (Playwright) ---
# -----------------------------------

def run_flask_server():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)

def start_gui():
    print("Initializing GUI...")
    user_data_dir = os.path.join(BASE_DIR, "browser_profile")
    
    try:
        with sync_playwright() as p:
            print("Launching Browser in App Mode...")
            
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                viewport=None,
                args=["--no-first-run", "--disable-infobars", "--app=http://127.0.0.1:5000"],
                ignore_default_args=["--enable-automation"]
            )
            
            page = context.pages[0]
            
            if page.url == 'about:blank':
                page.goto('http://127.0.0.1:5000')

            print("Application Started successfully.")
            
            # --- بخش اصلاح شده برای جلوگیری از بسته شدن ---
            # استفاده از حلقه به جای wait_for_event برای اطمینان ۱۰۰ درصدی
            while not page.is_closed():
                try:
                    time.sleep(1) # هر ۱ ثانیه چک میکند (بدون فشار به CPU)
                except KeyboardInterrupt:
                    print("Force Exit by User (Ctrl+C)")
                    break
                except Exception:
                    break
            
            print("Browser window closed by user.")
            context.close()
            
    except Exception as e:
        print(f"GUI Error: {e}")
    finally:
        print("Exiting application...")
        os._exit(0)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask_server)
    flask_thread.daemon = True
    flask_thread.start()
    
    time.sleep(1.5)
    start_gui()
