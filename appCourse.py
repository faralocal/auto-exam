import sys
import time

def main():
    # دریافت آرگومان‌ها از app.py
    if len(sys.argv) < 3:
        print("Error: Missing arguments")
        return

    excel_file = sys.argv[1]
    workflow_file = sys.argv[2]

    print(f"--- Starting Process ---")
    print(f"Processing Users from: {excel_file}")
    print(f"Applying Workflow: {workflow_file}")
    
    # شبیه‌سازی پردازش
    time.sleep(1) 
    print("Step 1: Data loaded...")
    time.sleep(1)
    print("Step 2: Workflow applied successfully.")
    print("--- Done ---")

if __name__ == "__main__":
    main()
