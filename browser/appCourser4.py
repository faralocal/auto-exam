#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import random
import re
import sys
import time
import io
import ctypes
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from openpyxl import load_workbook
import requests
import html

# کتابخانه‌های Playwright
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

# ------------------ Logging System ------------------
# این متغیر برای ذخیره لاگ‌ها جهت ارسال به فلاسک استفاده می‌شود
LOG_CAPTURE_LIST = []

class ListHandler(logging.Handler):
    """یک هندلر سفارشی برای ذخیره لاگ‌ها در لیست"""
    def emit(self, record):
        msg = self.format(record)
        LOG_CAPTURE_LIST.append(msg)
        # همچنین در کنسول هم چاپ شود
        print(msg)

# تنظیمات اولیه لاگر
logger = logging.getLogger("workflow")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")

# هندلر فایل (اختیاری)
file_handler = logging.FileHandler("workflow.log", encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# هندلر لیست (برای ارتباط با فلاسک)
list_handler = ListHandler()
list_handler.setFormatter(formatter)
logger.addHandler(list_handler)

# ------------------ Helpers ------------------

def get_key(d: Dict[str, Any], key: str, *alts: str, default=None):
    if key in d:
        return d[key]
    for a in alts:
        if a in d:
            return d[a]
    for k in d.keys():
        if k.lower() == key.lower():
            return d[k]
    return default

def to_int_or_none(x) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(x)
    except Exception:
        return None

def normalize_class_selector(cls_value: Optional[str]) -> str:
    if not cls_value:
        return ""
    s = cls_value.strip()
    if s.startswith("."):
        return s
    parts = [p for p in s.split() if p]
    return "." + ".".join(parts) if parts else ""

def build_css_selector(tag: Optional[str], cls: Optional[str], attr: Optional[str], value: Optional[str]) -> str:
    t = (tag or "*").strip()
    c = normalize_class_selector(cls)
    a = ""
    if attr and value is not None:
        a = f'[{attr}="{value}"]'
    elif attr:
        a = f"[{attr}]"
    return f"{t}{c}{a}"

def step_sleep(seconds: Optional[float]):
    if seconds is None:
        return
    try:
        s = float(seconds)
    except Exception:
        s = 0
    if s > 0:
        time.sleep(s)

def make_safe_filename(name: str, default: str, ext: str) -> str:
    base = (name or "").strip() or default
    base = re.sub(r'[\\/*?:"<>|]', "_", base)
    if ext and not base.lower().endswith(ext.lower()):
        base += ext
    return base

def get_locator_root(page, current_frame=None, parent=None):
    if parent is not None:
        return parent
    if current_frame is not None:
        return current_frame
    return page

def human_type(element, text: str):
    """تایپ انسانی با تاخیر تصادفی"""
    for ch in text:
        element.type(ch)
        extra = random.randint(100, 200) / 1000 if ch == " " else 0
        time.sleep(random.randint(50, 150) / 1000 + extra)

def get_desktop_size() -> Tuple[int, int]:
    try:
        user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
        if user32:
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        else:
            # Linux fallback
            return 1366, 768
    except Exception:
        return 1366, 768

# ------------------ Excel Helper ------------------

def load_excel_rows(file_path: str, start_row: int = 2) -> List[List[str]]:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Excel file not found: {file_path}")
    
    wb = load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active
    rows = []
    
    for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if idx < start_row:
            continue
        clean_row = [str(cell) if cell is not None else "" for cell in row]
        rows.append(clean_row)
    
    wb.close()
    logger.info(f"📊 Loaded {len(rows)} rows from Excel (starting at row {start_row})")
    return rows

# ------------------ Core Logic Functions ------------------

def check_condition(page, condition: Dict[str, Any], current_frame=None, parent=None) -> bool:
    status = get_key(condition, "status")
    tag = get_key(condition, "tag")
    attr = get_key(condition, "attr", "arrt", "attribute")
    value = get_key(condition, "value")
    cls = get_key(condition, "class")
    text = get_key(condition, "text")

    if not status:
        raise RuntimeError('Condition missing "status" (found/not_found)')

    selector = build_css_selector(tag, cls, attr, value)
    root = get_locator_root(page, current_frame, parent)
    loc = root.locator(selector)

    if text:
        loc = loc.filter(has_text=text)

    count = loc.count()
    logger.info(f"🔍 Condition check: {selector} status={status}, found={count} elements")

    if status == "found":
        return count > 0
    elif status == "not_found":
        return count == 0
    else:
        raise RuntimeError(f'Unknown condition status: "{status}"')

def switch_to_frame(page, step: Dict[str, Any]):
    frame_selector = get_key(step, "selector")
    frame_name = get_key(step, "name")
    frame_url = get_key(step, "url")
    frame_index = to_int_or_none(get_key(step, "index"))

    if frame_selector:
        logger.info(f"🖼️ Switching to frame by selector: {frame_selector}")
        return page.frame_locator(frame_selector)
    elif frame_name:
        logger.info(f"🖼️ Switching to frame by name: {frame_name}")
        frame = page.frame(name=frame_name)
        if not frame:
            raise RuntimeError(f"Frame with name '{frame_name}' not found.")
        return frame
    elif frame_url:
        logger.info(f"🖼️ Switching to frame by URL: {frame_url}")
        for frame in page.frames:
            if frame_url in frame.url:
                return frame
        raise RuntimeError(f"Frame with URL containing '{frame_url}' not found.")
    elif frame_index is not None:
        logger.info(f"🖼️ Switching to frame by index: {frame_index}")
        frames = page.frames
        if frame_index < 0 or frame_index >= len(frames):
            raise RuntimeError(f"Frame index {frame_index} out of range")
        return frames[frame_index]
    else:
        raise RuntimeError('Frame step requires: selector, name, url, or index')

def wait_and_click(loc, index: int = 0, timeout: float = 35000, ignore_error: bool = False):
    try:
        count = loc.count()
        if count == 0:
            if ignore_error:
                logger.warning("🚫 No matching elements found, but ignoring error.")
                return False
            raise RuntimeError("🚫 No matching elements found.")

        if index < 0 or index >= count:
            if ignore_error:
                logger.warning(f"🚫 Index {index} out of range (found {count}), ignoring.")
                return False
            raise RuntimeError(f"Index {index} out of range (found {count}).")

        target = loc.nth(index)
        target.wait_for(state="visible", timeout=timeout)
        target.scroll_into_view_if_needed()

        # Check if it's a link to wait for navigation
        is_link = False
        try:
            is_link = bool(target.get_attribute("href"))
        except Exception:
            pass

        target.click(timeout=timeout)

        if is_link:
            try:
                target.page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                time.sleep(2)
        return True

    except Exception as e:
        if ignore_error:
            logger.warning(f"⚠️ Click failed but ignoring: {str(e).split(':')[0]}")
            return False
        raise RuntimeError(f"Element interaction failed: {str(e).split(':')[0]}") from e

# ------------------ Download Functions ------------------

def extract_vtt_content(html_content):
    pre_match = re.search(r"<pre[^>]*>(.*?)</pre>", html_content, re.DOTALL | re.IGNORECASE)
    if pre_match:
        content = pre_match.group(1)
        content = re.sub(r"<[^>]+>", "", content)
        content = html.unescape(content).strip()
        logger.info("✅ VTT content extracted from <pre> tag")
        return content
    
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html_content, re.DOTALL | re.IGNORECASE)
    if body_match:
        content = body_match.group(1)
        content = re.sub(r"<[^>]+>", "", content)
        content = html.unescape(content).strip()
        logger.info("⚠️ VTT content extracted from body")
        return content
        
    return html_content

def download_subtitle_direct(url, output_path, page_context):
    logger.info(f"🎬 Downloading subtitle from: {url}")
    try:
        new_page = page_context.new_page()
        # Stealth scripts
        new_page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")
        
        response = new_page.goto(url, wait_until="networkidle", timeout=60000)
        
        if not response:
            logger.error("❌ Response not received")
            new_page.close()
            return False

        if response.status == 202:
            logger.info("⏳ Status 202, waiting for content...")
            time.sleep(5) # Wait for generation
        
        html_content = new_page.content()
        vtt_content = extract_vtt_content(html_content)

        if not vtt_content or len(vtt_content) < 10:
            logger.error("❌ Extracted content is empty or too short")
            new_page.close()
            return False

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(vtt_content)
        
        logger.info(f"✅ Subtitle saved: {output_path}")
        new_page.close()
        return True

    except Exception as e:
        logger.error(f"❌ Subtitle download error: {str(e)}")
        return False

def download_requests(url, out_path, retries=3):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    }
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                if r.status_code not in (200, 202, 206):
                    time.sleep(1)
                    continue
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=16384):
                        if chunk:
                            f.write(chunk)
            logger.info(f"Saved to {out_path}")
            return True
        except Exception as e:
            logger.warning(f"Download attempt {attempt} failed: {e}")
            time.sleep(1)
    return False

# ------------------ Execution Steps (Executors) ------------------

def exec_step_goto(page, step):
    url = get_key(step, "value", "url")
    if not url:
        raise RuntimeError('goto step missing "url"')
    logger.info(f"🌐 Navigating to: {url}")
    page.goto(url)
    step_sleep(get_key(step, "sleep"))

def exec_step_click(page, step, current_frame=None, parent=None):
    condition = get_key(step, "if")
    if condition:
        if check_condition(page, condition, current_frame, parent):
            logger.info("🔄 Condition met, executing alternative clicks")
            alt_clicks = get_key(condition, "click", default=[])
            if not isinstance(alt_clicks, list): alt_clicks = [alt_clicks]
            for ac in alt_clicks:
                exec_step_click(page, ac, current_frame, parent)
            return

    tag = get_key(step, "tag")
    attr = get_key(step, "attr", "attribute")
    value = get_key(step, "value")
    cls = get_key(step, "class")
    text = get_key(step, "text")
    idx = to_int_or_none(get_key(step, "array_select_one"))
    ignore_error = get_key(step, "ignore", default=False)

    selector = build_css_selector(tag, cls, attr, value)
    root = get_locator_root(page, current_frame, parent)
    loc = root.locator(selector)
    if text: loc = loc.filter(has_text=text)

    logger.info(f"🔘 Click: {selector} {f'| text={text}' if text else ''}")
    
    try:
        success = wait_and_click(loc, index=idx or 0, timeout=float(get_key(step, "timeout", default=45000)), ignore_error=ignore_error)
        if not success and ignore_error: return
    except PWTimeout as e:
        if ignore_error: logger.warning(f"⚠️ Timeout ignoring: {selector}")
        else: raise RuntimeError(f"Timeout: {selector}") from e
    
    step_sleep(get_key(step, "sleep"))

def exec_step_write(page, step, current_frame=None, parent=None):
    text = get_key(step, "write", "value", "text")
    if text is None: raise RuntimeError("Write step missing text")
    
    tag = get_key(step, "tag")
    attr = get_key(step, "attr", "attribute")
    value = get_key(step, "value")
    cls = get_key(step, "class")
    text_filter = get_key(step, "text") # for filtering element, not writing
    idx = to_int_or_none(get_key(step, "array_select_one"))

    selector = build_css_selector(tag, cls, attr, value)
    root = get_locator_root(page, current_frame, parent)
    loc = root.locator(selector)
    if text_filter: loc = loc.filter(has_text=text_filter)

    logger.info(f"⌨️ Writing '{text}' to: {selector}")
    
    target = loc.nth(idx or 0)
    target.wait_for(state="visible", timeout=35000)
    target.scroll_into_view_if_needed()
    target.click()
    if get_key(step, "clear", default=True):
        target.clear()
    human_type(target, str(text))

def exec_step_write_excel(page, step, current_row, current_frame=None, parent=None):
    col_index = to_int_or_none(get_key(step, "write_from_col"))
    if not col_index or col_index < 1:
        raise RuntimeError('write_excel requires "write_from_col" >= 1')
    
    cell_value = current_row[col_index - 1] if (col_index - 1) < len(current_row) else ""
    
    # Create a temporary step dict to reuse exec_step_write logic
    temp_step = step.copy()
    temp_step["write"] = cell_value
    exec_step_write(page, temp_step, current_frame, parent)

def exec_step_download_from_link(page, step, current_frame=None, parent=None):
    tag = get_key(step, "tag")
    attr = get_key(step, "attr", "attribute")
    value = get_key(step, "value")
    cls = get_key(step, "class")
    text = get_key(step, "text")
    idx = to_int_or_none(get_key(step, "array_select_one"))
    download_dir = get_key(step, "download_dir", default=os.getcwd())
    file_extension = get_key(step, "extension", "ext")
    index = get_key(step, "index", default=1)
    ignore_error = get_key(step, "ignore", default=False)

    selector = build_css_selector(tag, cls, attr, value)
    root = get_locator_root(page, current_frame, parent)
    loc = root.locator(selector)
    if text: loc = loc.filter(has_text=text)

    logger.info(f"📥 Download Link: {selector}")

    try:
        target = loc.nth(idx or 0)
        target.wait_for(state="visible", timeout=35000)
        target.scroll_into_view_if_needed()
        
        download_url = target.get_attribute("href")
        if not download_url:
            raise RuntimeError("No href found")
        
        if not download_url.startswith("http"):
            download_url = urljoin(page.url, download_url)

        # Detect Extension
        if not file_extension:
            parsed = urlparse(download_url)
            if "." in parsed.path:
                file_extension = parsed.path.split(".")[-1]
        
        if file_extension:
            file_extension = "." + file_extension.replace(".", "")
        else:
            file_extension = ".mp4"

        # Filename
        page_title = page.title() or "download"
        safe_title = make_safe_filename(page_title, "download", "")
        out_path = os.path.join(download_dir, f"{safe_title}_{index}{file_extension}")
        os.makedirs(download_dir, exist_ok=True)

        success = False
        if file_extension.lower() in [".vtt", ".srt"]:
            success = download_subtitle_direct(download_url, out_path, page.context)
        
        if not success:
            success = download_requests(download_url, out_path)
            
        if success:
            logger.info(f"✅ Downloaded: {out_path}")
        else:
            logger.error("❌ Download failed")

    except Exception as e:
        if ignore_error: logger.warning(f"⚠️ Download error ignored: {e}")
        else: raise

def exec_step_group_excel(page, browser, step, current_frame=None, parent=None):
    file_path = get_key(step, "file")
    start_row = to_int_or_none(get_key(step, "start_row")) or 2
    actions = get_key(step, "actions", default=[])
    
    if not file_path or not actions:
        raise RuntimeError("group_excel missing file or actions")

    rows = load_excel_rows(file_path, start_row)
    if not rows:
        logger.warning("⚠️ No rows in Excel")
        return

    for row_index, current_row in enumerate(rows):
        logger.info(f"🧮 Processing Excel Row {row_index + start_row}")
        
        for action in actions:
            # Handle write_excel specifically
            if action.get("type") == "write_excel":
                exec_step_write_excel(page, action, current_row, current_frame, parent)
            else:
                # Recursively call dispatcher
                dispatch_step(page, browser, action, current_frame, parent)

def exec_step_array(page, step, current_frame=None, parent=None):
    tag = get_key(step, "tag")
    cls = get_key(step, "class")
    filter_text = get_key(step, "if_find_text_inside")
    
    selector = build_css_selector(tag, cls, None, None)
    root = get_locator_root(page, current_frame, parent)
    parents = root.locator(selector)
    if filter_text: parents = parents.filter(has_text=filter_text)
    
    total = parents.count()
    logger.info(f"🔍 Array found {total} elements for {selector}")
    
    clicks = get_key(step, "click", default=[])
    
    for i in range(total):
        logger.info(f"  Processing array item {i+1}/{total}")
        p = parents.nth(i)
        for child_action in clicks:
            # Dispatch child actions using 'p' as parent
            dispatch_step(page, None, child_action, current_frame, parent=p)

def dispatch_step(page, browser, step, current_frame=None, parent=None):
    """تابع مرکزی توزیع کننده دستورات"""
    stype = get_key(step, "type")
    if not stype: return

    stype_l = str(stype).strip().lower()
    ignore = get_key(step, "ignore", default=False)
    title = get_key(step, "title", default=stype_l)

    logger.info(f"▶️ Executing: {title} ({stype_l})")

    try:
        if stype_l == "goto": exec_step_goto(page, step)
        elif stype_l == "click": exec_step_click(page, step, current_frame, parent)
        elif stype_l == "write": exec_step_write(page, step, current_frame, parent)
        elif stype_l == "write_excel": raise RuntimeError("write_excel must be inside group_excel")
        elif stype_l == "group_excel": exec_step_group_excel(page, browser, step, current_frame, parent)
        elif stype_l == "array": exec_step_array(page, step, current_frame, parent)
        elif stype_l == "download_from_link": exec_step_download_from_link(page, step, current_frame, parent)
        elif stype_l == "frame": switch_to_frame(page, step) # This needs better state handling if nested
        elif stype_l == "refresh": page.reload()
        # Add other types as needed...
        else:
            if not ignore: logger.warning(f"Unknown step type: {stype_l}")

    except Exception as e:
        if ignore:
            logger.warning(f"⚠️ Ignored error in {title}: {e}")
        else:
            raise e
    
    step_sleep(get_key(step, "sleep"))

# ------------------ Main Runner ------------------

def run(workflow: List[Dict[str, Any]], start_url: Optional[str] = None, profile_dir: Optional[str] = None):
    """
    تابع اصلی اجرای ورک‌فلو که مرورگر را باز می‌کند و استپ‌ها را اجرا می‌کند.
    """
    width, height = 1366, 768
    
    # اگر پروفایل مشخص نشده بود، از یک پوشه جداگانه استفاده کن
    if not profile_dir:
        # اصلاح مسیر برای جلوگیری از ایجاد پوشه در جای اشتباه
        current_dir = os.getcwd()
        # در حالت دولوپمنت ممکن است current_dir پوشه روت باشد، پس مستقیم میسازیم
        profile_dir = os.path.join(current_dir, "automation_profile")
    
    logger.info(f"🚀 Starting Run. Profile: {profile_dir}")
    
    args = [
        f"--window-size={width},{height}",
        "--start-maximized",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
    ]

    with sync_playwright() as p:
        # Launch Persistent Context
        # توجه: اگر پوشه قفل مانده باشد (از کرش قبلی)، سعی میکنیم هندل کنیم
        try:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                args=args,
                viewport={"width": width, "height": height},
                accept_downloads=True,
            )
        except Exception as e:
            if "SingletonLock" in str(e):
                logger.warning("⚠️ Profile is locked. Attempting to use a temporary profile name...")
                # اگر باز هم قفل بود، یک نام رندوم موقت بده تا کار کاربر راه بیفتد
                profile_dir = profile_dir + f"_temp_{random.randint(1000,9999)}"
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    headless=False,
                    args=args,
                    viewport={"width": width, "height": height},
                    accept_downloads=True,
                )
            else:
                raise e

        try:
            # Stealth Script
            browser.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")
            
            page = browser.pages[0] if browser.pages else browser.new_page()

            if start_url:
                page.goto(start_url)

            # Loop through workflow
            for i, step in enumerate(workflow):
                dispatch_step(page, browser, step)

            logger.info("✅ Workflow Finished Successfully.")
            
            time.sleep(2)
            browser.close()

        except Exception as e:
            logger.error(f"❌ Critical Error: {e}")
            browser.close()
            raise e


# ------------------ Integration Point ------------------

def run_course_automation(workflow_path):
    """
    این تابع توسط app.py صدا زده می‌شود.
    وظیفه: خواندن فایل، اجرای run و برگرداندن لاگ‌ها.
    """
    global LOG_CAPTURE_LIST
    LOG_CAPTURE_LIST.clear() # پاک کردن لاگ‌های قبلی
    
    logs_output = []
    
    try:
        if not os.path.exists(workflow_path):
            raise FileNotFoundError(f"Workflow file not found: {workflow_path}")
        
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow_data = json.load(f)
            
        logger.info(f"📂 Loaded workflow: {workflow_path}")
        
        # اجرای واقعی
        run(workflow_data)
        
        return True, "\n".join(LOG_CAPTURE_LIST)

    except Exception as e:
        logger.error(f"🔥 Execution Failed: {str(e)}")
        # اضافه کردن خطا به لاگ‌ها
        return False, "\n".join(LOG_CAPTURE_LIST)

# ------------------ CLI Test ------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--workflow', required=True)
    args = parser.parse_args()
    
    success, log_out = run_course_automation(args.workflow)
    print("\n--- FINAL OUTPUT ---")
    print(log_out)
