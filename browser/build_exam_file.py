import json
import os
import re
import sys
import pandas as pd
from typing import Any, Dict, List, Union

# ---------------------------------------------------------
# منطق اصلی ادغام فایل‌ها (Refactored Logic)
# ---------------------------------------------------------
def merge_logic(input_dir: str, output_path: str, excel_full_path: str, log_callback) -> bool:
    """
    این تابع منطق اصلی ادغام فایل‌های جیسون و ساختار اکسل را انجام می‌دهد.
    log_callback: تابعی است که پیام‌ها را ذخیره یا چاپ می‌کند.
    """
    
    if not os.path.isdir(input_dir):
        log_callback(f"Error: The specified path '{input_dir}' is not a valid directory!")
        return False

    # بررسی پسوند فایل خروجی
    if not output_path.lower().endswith(".json"):
        log_callback("Error: Output file must have a .json extension!")
        return False

    # پیدا کردن فایل‌های جیسون عددی (مثل 1.json, 2.json)
    json_files = [
        f for f in os.listdir(input_dir)
        if f.lower().endswith(".json") and re.match(r"^\d+\.json$", f, re.IGNORECASE)
    ]

    if not json_files:
        log_callback("No valid JSON files with numeric names found in the directory!")
        return False

    # مرتب‌سازی عددی فایل‌ها
    sorted_files = sorted(json_files, key=lambda x: int(os.path.splitext(x)[0]))
    
    log_callback(f"\nFound {len(sorted_files)} valid JSON files")
    log_callback(f"Processing files in order: {', '.join(sorted_files)}")

    merged_data: List[Dict[str, Any]] = []
    errors = []
    warnings = []

    # خواندن و ادغام فایل‌ها
    for file_name in sorted_files:
        file_path = os.path.join(input_dir, file_name)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)

            if not isinstance(content, list):
                errors.append(f"File {file_name} does not contain a valid JSON array")
                continue

            # هندل کردن حالت خاص group_excel (اگر فایل‌های جزئی خودشان دارای این ساختار باشند)
            if (excel_full_path and content and isinstance(content[0], dict) and content[0].get("type") == "group_excel"):
                if len(content) > 1:
                    warnings.append(f"File {file_name} has additional elements after group_excel. Only actions used.")
                
                actions = content[0].get("actions", [])
                if not isinstance(actions, list):
                    errors.append(f"Invalid 'actions' field in group_excel object in {file_name}")
                else:
                    merged_data.extend(actions)
                    log_callback(f"✅ Processed {file_name} as group_excel (extracted {len(actions)} actions)")
            else:
                merged_data.extend(content)
                log_callback(f"✅ Successfully processed {file_name} ({len(content)} items)")

        except json.JSONDecodeError as e:
            errors.append(f"JSON decode error in {file_name}: {str(e)}")
        except Exception as e:
            errors.append(f"Error processing {file_name}: {str(e)}")

    # گزارش هشدارها
    if warnings:
        log_callback("\n⚠️ Warnings encountered:")
        for i, warn in enumerate(warnings, 1):
            log_callback(f"  {i}. {warn}")

    # گزارش خطاها
    if errors:
        log_callback("\n❌ Errors encountered:")
        for i, err in enumerate(errors, 1):
            log_callback(f"  {i}. {err}")

    if not merged_data:
        log_callback("No valid data to merge. Aborting.")
        return False

    # --- ساختار نهایی (Wrapping) ---
    final_data: Union[List, List[Dict[str, Any]]] = merged_data

    # اگر فایل اکسل انتخاب شده باشد، داده‌ها را داخل ساختار group_excel می‌گذاریم
    if excel_full_path:
        # نکته مهم: معمولاً در فایل جیسون فقط نام فایل اکسل نیاز است نه مسیر کامل
        # اما اینجا مسیر کاملی که از app.py آمده را به جیسون می‌دهیم.
        # اگر اتوماسیون شما فقط نام فایل را می‌خواهد، خط زیر را آنکامنت کنید:
        # excel_name_only = os.path.basename(excel_full_path)
        
        final_data = [
            {
                "type": "group_excel",
                "file": excel_full_path, # یا excel_name_only
                "start_row": 2,
                "actions": merged_data,
            }
        ]
        log_callback(f"\nℹ️ Wrapped {len(merged_data)} items in group_excel structure")

    # ذخیره فایل نهایی
    try:
        output_dir_path = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(output_dir_path, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)

        log_callback(f"\n✅ Successfully saved output to: {output_path}")
        log_callback(f"Total items: {len(merged_data)}")
        log_callback(f"File size: {os.path.getsize(output_path) / 1024:.2f} KB")
        return True

    except Exception as e:
        log_callback(f"\n❌ Error saving output file: {str(e)}")
        return False


# ---------------------------------------------------------
# تابعی که توسط app.py صدا زده می‌شود
# ---------------------------------------------------------
def process_exam(excel_path, input_dir, output_path):
    """
    این تابع واسط بین فلاسک و منطق اصلی مرج کردن است.
    """
    logs = []

    # یک تابع داخلی برای لاگ کردن که هم پرینت کند هم در لیست ذخیره کند
    def logger(message):
        print(message)
        logs.append(str(message))

    logger(f"--- Starting Build Process ---")
    logger(f"Excel File: {excel_path}")
    logger(f"Input Dir:  {input_dir}")
    logger(f"Output File: {output_path}")

    try:
        # فراخوانی منطق اصلی که در بالا نوشتیم
        success = merge_logic(
            input_dir=input_dir, 
            output_path=output_path, 
            excel_full_path=excel_path, 
            log_callback=logger
        )
        
        return success, "\n".join(logs)

    except Exception as e:
        logger(f"Critical Error in process_exam: {str(e)}")
        return False, "\n".join(logs)


# برای تست دستی در ترمینال
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--excel', required=False, help="Path to excel file")
    parser.add_argument('--input_dir', required=True, help="Folder with json files")
    parser.add_argument('--output', required=True, help="Output json path")
    args = parser.parse_args()

    success, output_log = process_exam(args.excel, args.input_dir, args.output)
    print("\n--- Final Output Log ---")
    print(output_log)
