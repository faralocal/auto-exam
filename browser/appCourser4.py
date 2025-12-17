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
LOG_CAPTURE_LIST = []

class ListHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            LOG_CAPTURE_LIST.append(msg)
            print(msg)
        except Exception:
            pass

logger = logging.getLogger("workflow")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")

if logger.hasHandlers():
    logger.handlers.clear()

file_handler = logging.FileHandler("workflow.log", encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

list_handler = ListHandler()
list_handler.setFormatter(formatter)
logger.addHandler(list_handler)

# ------------------ Helpers ------------------

def get_key(d: Dict[str, Any], key: str, *alts: str, default=None):
    if key in d: return d[key]
    for a in alts:
        if a in d: return d[a]
    for k in d.keys():
        if k.lower() == key.lower(): return d[k]
    return default

def to_int_or_none(x) -> Optional[int]:
    if x is None: return None
    try: return int(x)
    except: return None

def normalize_class_selector(cls_value: Optional[str]) -> str:
    if not cls_value: return ""
    s = cls_value.strip()
    if s.startswith("."): return s
    parts = [p for p in s.split() if p]
    return "." + ".".join(parts) if parts else ""

def build_css_selector(tag: Optional[str], cls: Optional[str], attr: Optional[str], value: Optional[str]) -> str:
    t = (tag or "*").strip()
    c = normalize_class_selector(cls)
    a = ""
    if attr and value is not None: a = f'[{attr}="{value}"]'
    elif attr: a = f"[{attr}]"
    return f"{t}{c}{a}"

def step_sleep(seconds: Optional[float]):
    if seconds is None: return
    try:
        s = float(seconds)
        if s > 0: time.sleep(s)
    except: pass

def make_safe_filename(name: str, default: str, ext: str) -> str:
    base = (name or "").strip() or default
    base = re.sub(r'[\\/*?:"<>|]', "_", base)
    if ext and not base.lower().endswith(ext.lower()):
        base += ext
    return base

def get_locator_root(page, current_frame=None, parent=None):
    if parent is not None: return parent
    if current_frame is not None: return current_frame
    return page

def human_type(element, text: str):
    for ch in str(text):
        element.type(ch)
        time.sleep(random.randint(50, 150) / 1000)

# ------------------ Excel Helper ------------------

def load_excel_rows(file_path: str, start_row: int = 2) -> List[List[str]]:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Excel file not found: {file_path}")
    
    wb = load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if idx < start_row: continue
        clean_row = [str(cell) if cell is not None else "" for cell in row]
        rows.append(clean_row)
    wb.close()
    logger.info(f"📊 Loaded {len(rows)} rows from Excel")
    return rows

# ------------------ Download Helpers (VTT/SRT) ------------------

def extract_vtt_content(html_content):
    pre_match = re.search(r"<pre[^>]*>(.*?)</pre>", html_content, re.DOTALL | re.IGNORECASE)
    if pre_match:
        content = pre_match.group(1)
        content = re.sub(r"<[^>]+>", "", content)
        content = html.unescape(content).strip()
        return content
    
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html_content, re.DOTALL | re.IGNORECASE)
    if body_match:
        content = body_match.group(1)
        content = re.sub(r"<[^>]+>", "", content)
        content = html.unescape(content).strip()
        return content
    return html_content

def download_subtitle_direct(url, output_path, page_context):
    logger.info(f"🎬 Subtitle download: {url}")
    try:
        new_page = page_context.new_page()
        new_page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")
        response = new_page.goto(url, wait_until="networkidle", timeout=60000)
        
        if not response:
            new_page.close(); return False

        if response.status == 202:
            time.sleep(5)
        
        html_content = new_page.content()
        vtt_content = extract_vtt_content(html_content)

        if not vtt_content or len(vtt_content) < 10:
            new_page.close(); return False

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(vtt_content)
        new_page.close()
        return True
    except Exception as e:
        logger.error(f"Subtitle error: {e}")
        return False

# ------------------ Core Functions ------------------

def check_condition(page, condition: Dict[str, Any], current_frame=None, parent=None) -> bool:
    status = get_key(condition, "status")
    tag = get_key(condition, "tag")
    attr = get_key(condition, "attr", "attribute")
    value = get_key(condition, "value")
    cls = get_key(condition, "class")
    text = get_key(condition, "text")

    if not status: raise RuntimeError('Condition missing "status"')

    selector = build_css_selector(tag, cls, attr, value)
    root = get_locator_root(page, current_frame, parent)
    loc = root.locator(selector)
    if text: loc = loc.filter(has_text=text)

    count = loc.count()
    logger.info(f"🔍 Condition: {selector} status={status}, found={count}")

    if status == "found": return count > 0
    elif status == "not_found": return count == 0
    else: raise RuntimeError(f'Unknown status: "{status}"')

def switch_to_frame(page, step: Dict[str, Any]):
    frame_selector = get_key(step, "selector")
    frame_name = get_key(step, "name")
    frame_url = get_key(step, "url")
    frame_index = to_int_or_none(get_key(step, "index"))

    if frame_selector:
        logger.info(f"🖼️ Switch frame by selector: {frame_selector}")
        return page.frame_locator(frame_selector)
    elif frame_name:
        logger.info(f"🖼️ Switch frame by name: {frame_name}")
        return page.frame(name=frame_name)
    elif frame_url:
        logger.info(f"🖼️ Switch frame by URL: {frame_url}")
        for frame in page.frames:
            if frame_url in frame.url: return frame
        raise RuntimeError(f"Frame URL '{frame_url}' not found.")
    elif frame_index is not None:
        logger.info(f"🖼️ Switch frame by index: {frame_index}")
        return page.frames[frame_index]
    else:
        raise RuntimeError('Frame step requires selector, name, url, or index')

def wait_and_click(loc, index: int = 0, timeout: float = 35000, ignore_error: bool = False):
    try:
        count = loc.count()
        if count == 0:
            if ignore_error: return False
            raise RuntimeError("No matching elements found.")

        target = loc.nth(index)
        target.wait_for(state="visible", timeout=timeout)
        target.scroll_into_view_if_needed()
        
        is_link = False
        try:
            if target.get_attribute("href"): is_link = True
        except: pass

        target.click(timeout=timeout)

        if is_link:
            try: target.page.wait_for_load_state("networkidle", timeout=15000)
            except: pass
        return True
    except Exception as e:
        if ignore_error: 
            logger.warning(f"⚠️ Click ignored: {e}")
            return False
        raise RuntimeError(f"Click failed: {e}") from e

# ------------------ Steps Executors ------------------

def exec_step_goto(page, step):
    url = get_key(step, "value", "url")
    if not url: raise RuntimeError('goto missing url')
    logger.info(f"🌐 Goto: {url}")
    page.goto(url)
    step_sleep(get_key(step, "sleep"))

def exec_step_refresh(page, step):
    logger.info("🔄 Refreshing page")
    page.reload()
    step_sleep(get_key(step, "sleep"))

def exec_step_click(page, step, current_frame=None, parent=None):
    condition = get_key(step, "if")
    if condition:
        if check_condition(page, condition, current_frame, parent):
            alt_clicks = get_key(condition, "click", default=[])
            if not isinstance(alt_clicks, list): alt_clicks = [alt_clicks]
            for ac in alt_clicks:
                dispatch_step(page, None, ac, current_frame, parent) 
            return

    tag = get_key(step, "tag")
    attr = get_key(step, "attr", "attribute")
    value = get_key(step, "value")
    cls = get_key(step, "class")
    text = get_key(step, "text")
    idx = to_int_or_none(get_key(step, "array_select_one")) or 0
    ignore = get_key(step, "ignore", default=False)
    timeout = float(get_key(step, "timeout", default=30000))

    selector = build_css_selector(tag, cls, attr, value)
    root = get_locator_root(page, current_frame, parent)
    loc = root.locator(selector)
    if text: loc = loc.filter(has_text=text)

    logger.info(f"🔘 Click: {selector}")
    try:
        wait_and_click(loc, index=idx, timeout=timeout, ignore_error=ignore)
    except Exception as e:
        if not ignore: raise e
    
    step_sleep(get_key(step, "sleep"))

def exec_step_write(page, step, current_frame=None, parent=None):
    text = get_key(step, "write", "value", "text")
    tag = get_key(step, "tag")
    cls = get_key(step, "class")
    attr = get_key(step, "attr", "attribute")
    value = get_key(step, "value")
    idx = to_int_or_none(get_key(step, "array_select_one")) or 0
    ignore = get_key(step, "ignore", default=False)
    timeout = float(get_key(step, "timeout", default=30000))

    selector = build_css_selector(tag, cls, attr, value)
    root = get_locator_root(page, current_frame, parent)
    loc = root.locator(selector)

    logger.info(f"⌨️ Writing to: {selector}")
    
    # ✅ FIX: Handle ignore error
    try:
        target = loc.nth(idx)
        target.wait_for(state="visible", timeout=timeout)
        target.scroll_into_view_if_needed()
        target.click()
        if get_key(step, "clear", default=True): target.clear()
        human_type(target, text)
    except Exception as e:
        if ignore:
            logger.warning(f"⚠️ Write ignored error: {e}")
        else:
            raise e
            
    step_sleep(get_key(step, "sleep"))

def exec_step_select(page, step, current_frame=None, parent=None):
    tag = get_key(step, "tag", default="select")
    cls = get_key(step, "class")
    attr = get_key(step, "attr", "attribute")
    value = get_key(step, "value")
    idx = to_int_or_none(get_key(step, "array_select_one")) or 0
    ignore = get_key(step, "ignore", default=False)
    timeout = float(get_key(step, "timeout", default=30000))
    
    opt_val = get_key(step, "option_value")
    opt_lbl = get_key(step, "option_label")
    opt_idx = to_int_or_none(get_key(step, "option_index"))

    selector = build_css_selector(tag, cls, attr, value)
    root = get_locator_root(page, current_frame, parent)
    loc = root.locator(selector)
    
    logger.info(f"🔽 Select: {selector}")
    
    # ✅ FIX: Handle ignore error
    try:
        target = loc.nth(idx)
        target.wait_for(state="visible", timeout=timeout)
        target.scroll_into_view_if_needed()
        
        select_args = {}
        if opt_val is not None: select_args["value"] = opt_val
        if opt_lbl is not None: select_args["label"] = opt_lbl
        if opt_idx is not None: select_args["index"] = opt_idx
        
        target.select_option(**select_args)
    except Exception as e:
        if ignore:
            logger.warning(f"⚠️ Select ignored error: {e}")
        else:
            raise e
            
    step_sleep(get_key(step, "sleep"))

def exec_step_scroll(page, step, current_frame=None, parent=None):
    x = get_key(step, "x")
    y = get_key(step, "y")
    ignore = get_key(step, "ignore", default=False)
    timeout = float(get_key(step, "timeout", default=30000))

    if x is not None or y is not None:
        logger.info(f"📜 Scroll to position: {x}, {y}")
        page.evaluate(f"window.scrollTo({x or 0}, {y or 0})")
        return

    tag = get_key(step, "tag")
    cls = get_key(step, "class")
    attr = get_key(step, "attr")
    value = get_key(step, "value")
    text = get_key(step, "text")
    idx = to_int_or_none(get_key(step, "array_select_one")) or 0

    selector = build_css_selector(tag, cls, attr, value)
    root = get_locator_root(page, current_frame, parent)
    loc = root.locator(selector)
    if text: loc = loc.filter(has_text=text)

    logger.info(f"📜 Scroll to element: {selector}")
    
    # ✅ FIX: Handle ignore error
    try:
        target = loc.nth(idx)
        target.wait_for(state="visible", timeout=timeout)
        target.scroll_into_view_if_needed()
    except Exception as e:
        if ignore:
            logger.warning(f"⚠️ Scroll ignored error: {e}")
        else:
            raise e
            
    step_sleep(get_key(step, "sleep"))

def exec_step_use_last_tab(browser, step):
    if len(browser.pages) > 1:
        last = browser.pages[-1]
        last.bring_to_front()
        logger.info(f"📑 Switched to last tab: {last.url}")
    else:
        logger.info("ℹ️ Single tab open.")
    step_sleep(get_key(step, "sleep"))

def exec_step_main_frame(page, step):
    logger.info("🏠 Switch to Main Frame")
    step_sleep(get_key(step, "sleep"))
    return None 

def exec_step_array(page, step, current_frame=None, parent=None):
    tag = get_key(step, "tag")
    cls = get_key(step, "class")
    filter_text = get_key(step, "if_find_text_inside")
    
    selector = build_css_selector(tag, cls, None, None)
    root = get_locator_root(page, current_frame, parent)
    parents = root.locator(selector)
    if filter_text: parents = parents.filter(has_text=filter_text)
    
    total = parents.count()
    logger.info(f"🔍 Array found {total} items")
    
    clicks = get_key(step, "click", default=[])
    for i in range(total):
        p = parents.nth(i)
        for child_action in clicks:
            dispatch_step(page, None, child_action, current_frame, parent=p)

def exec_step_group_action(page, browser, step, current_frame=None, parent=None):
    # ✅ RESTORED: Full logic for finding parent elements before execution
    tag = get_key(step, "tag")
    cls = get_key(step, "class")
    attr = get_key(step, "attr", "attribute")
    value = get_key(step, "value")
    filter_text = get_key(step, "if_find_text_inside")
    idx = to_int_or_none(get_key(step, "array_select_one"))
    ignore = get_key(step, "ignore", default=False)
    actions = get_key(step, "actions", default=[])
    global_act = get_key(step, "global_actions", default=False)

    selector = build_css_selector(tag, cls, attr, value)
    root = get_locator_root(page, current_frame, parent)
    parents = root.locator(selector)
    if filter_text: parents = parents.filter(has_text=filter_text)

    total = parents.count()
    logger.info(f"🧩 Group Action: found {total} parents for {selector}")
    
    if total == 0:
        if ignore: return
        raise RuntimeError(f"No parents found for group_action: {selector}")

    indices = [idx] if idx is not None else range(total)
    
    for i in indices:
        if i >= total: continue
        p = parents.nth(i)
        
        # Determine effective parent
        effective_parent = None if global_act else p
        
        for action in actions:
            if get_key(action, "global", default=False):
                dispatch_step(page, browser, action, current_frame, parent=None)
            else:
                dispatch_step(page, browser, action, current_frame, parent=effective_parent)

def exec_step_group_excel(page, browser, step, current_frame=None, parent=None):
    file_path = get_key(step, "file")
    start_row = to_int_or_none(get_key(step, "start_row")) or 2
    actions = get_key(step, "actions", default=[])
    
    rows = load_excel_rows(file_path, start_row)
    for row_index, current_row in enumerate(rows):
        logger.info(f"🧮 Excel Row {row_index + start_row}")
        for action in actions:
            if action.get("type") == "write_excel":
                col = to_int_or_none(get_key(action, "write_from_col"))
                if col:
                    val = current_row[col - 1] if (col-1) < len(current_row) else ""
                    temp = action.copy()
                    temp["write"] = val
                    exec_step_write(page, temp, current_frame, parent)
            else:
                dispatch_step(page, browser, action, current_frame, parent)

def exec_step_download_from_link(page, step, current_frame=None, parent=None):
    # ✅ RESTORED: Full logic with VTT/Subtitle support
    tag = get_key(step, "tag")
    idx = to_int_or_none(get_key(step, "array_select_one")) or 0
    dl_dir = get_key(step, "download_dir", default=os.getcwd())
    ignore = get_key(step, "ignore", default=False)
    file_extension = get_key(step, "extension", "ext")
    index = get_key(step, "index", default=1)
    
    selector = build_css_selector(tag, get_key(step, "class"), get_key(step, "attr"), get_key(step, "value"))
    root = get_locator_root(page, current_frame, parent)
    loc = root.locator(selector)
    if get_key(step, "text"): loc = loc.filter(has_text=get_key(step, "text"))

    logger.info(f"📥 Download: {selector}")
    
    try:
        target = loc.nth(idx)
        target.wait_for(state="visible", timeout=35000)
        href = target.get_attribute("href")
        
        if href:
            if not href.startswith("http"): href = urljoin(page.url, href)
            
            # Extension detection
            if not file_extension:
                parsed = urlparse(href)
                if "." in parsed.path: file_extension = "." + parsed.path.split(".")[-1]
                else: file_extension = ".mp4"
            
            # Filename generation
            page_title = page.title() or "download"
            safe_title = make_safe_filename(page_title, "download", "")
            out_path = os.path.join(dl_dir, f"{safe_title}_{index}{file_extension}")
            os.makedirs(dl_dir, exist_ok=True)

            # Subtitle check
            success = False
            if file_extension.lower() in [".vtt", ".srt"]:
                success = download_subtitle_direct(href, out_path, page.context)
            
            if not success:
                try:
                    r = requests.get(href, stream=True, timeout=60)
                    with open(out_path, "wb") as f:
                        for chunk in r.iter_content(16384): f.write(chunk)
                    logger.info(f"✅ Downloaded: {out_path}")
                except Exception as ex:
                    logger.error(f"Download request failed: {ex}")
                    raise ex

    except Exception as e:
        if ignore: logger.warning(f"⚠️ Download ignored: {e}")
        else: raise e

# ------------------ Dispatcher ------------------

def dispatch_step(page, browser, step, current_frame=None, parent=None):
    stype = get_key(step, "type")
    if not stype: return current_frame

    stype_l = str(stype).strip().lower()
    ignore = get_key(step, "ignore", default=False)
    
    try:
        if stype_l == "frame": return switch_to_frame(page, step)
        elif stype_l == "main_frame": return exec_step_main_frame(page, step)
        elif stype_l == "goto": exec_step_goto(page, step)
        elif stype_l == "click": exec_step_click(page, step, current_frame, parent)
        elif stype_l == "write": exec_step_write(page, step, current_frame, parent)
        elif stype_l == "select": exec_step_select(page, step, current_frame, parent)
        elif stype_l == "scroll": exec_step_scroll(page, step, current_frame, parent)
        elif stype_l == "use_last_tab": exec_step_use_last_tab(browser, step)
        elif stype_l == "refresh": exec_step_refresh(page, step)
        elif stype_l == "group_excel": exec_step_group_excel(page, browser, step, current_frame, parent)
        elif stype_l == "array": exec_step_array(page, step, current_frame, parent)
        elif stype_l == "group_action": exec_step_group_action(page, browser, step, current_frame, parent)
        elif stype_l == "download_from_link": exec_step_download_from_link(page, step, current_frame, parent)
        else:
            if not ignore: logger.warning(f"Unknown step: {stype_l}")

    except Exception as e:
        if ignore: logger.warning(f"⚠️ Ignored Error in {stype_l}: {e}")
        else: raise e
    
    return current_frame

# ------------------ Main Runner ------------------

def run(workflow: List[Dict[str, Any]], start_url: Optional[str] = None, profile_dir: Optional[str] = None):
    width, height = 1366, 768
    
    if not profile_dir:
        base = os.getcwd()
        # Ensure we are not inside browser folder when creating automation_profile
        if base.endswith("browser"): base = os.path.dirname(base)
        profile_dir = os.path.join(base, "automation_profile")

    logger.info(f"🚀 Run started. Profile: {profile_dir}")
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
                viewport={"width": width, "height": height}
            )
        except Exception as e:
            if "SingletonLock" in str(e):
                logger.warning("⚠️ Profile locked. Using temp profile.")
                profile_dir += f"_{random.randint(1000,9999)}"
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    headless=False,
                    args=["--start-maximized"],
                    viewport={"width": width, "height": height}
                )
            else: raise e

        try:
            browser.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")
            page = browser.pages[0] if browser.pages else browser.new_page()
            if start_url: page.goto(start_url)

            current_frame = None
            for step in workflow:
                current_frame = dispatch_step(page, browser, step, current_frame)

            logger.info("✅ Done.")
            time.sleep(2)
            browser.close()

        except Exception as e:
            logger.error(f"❌ Error: {e}")
            browser.close()
            raise e

# ------------------ Integration Point ------------------

def run_course_automation(workflow_path):
    global LOG_CAPTURE_LIST
    LOG_CAPTURE_LIST.clear()
    
    try:
        if not os.path.exists(workflow_path): raise FileNotFoundError("Workflow file missing")
        with open(workflow_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        run(data)
        return True, "\n".join(LOG_CAPTURE_LIST)
    except Exception as e:
        return False, "\n".join(LOG_CAPTURE_LIST) + f"\nFATAL: {e}"

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--workflow', required=True)
    args = parser.parse_args()
    success, logs = run_course_automation(args.workflow)
    print(logs)
