
import pandas as pd
from pathlib import Path
import glob

# Find the latest output file
files = list(Path("output").glob("generated_mapping_*.xlsx"))
files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
latest_file = files[0]

print(f"Checking file: {latest_file}")

# Load the file
df = pd.read_excel(latest_file, sheet_name=" Inbound X12 to Oracle")

# Columns (assuming standard mapping template)
# B -> Segment/Element (index 1)
# C -> Value (index 2)
# J -> Constant values and Comments (index 9)

# Print first 20 mapped rows
print("\n--- Mapped Rows Sample ---")
count = 0
for idx, row in df.iterrows():
    # Check if B or C or J has content
    b_val = row.iloc[1] if len(row) > 1 else None
    c_val = row.iloc[2] if len(row) > 2 else None
    j_val = row.iloc[9] if len(row) > 9 else None
    
    if pd.notna(b_val) or pd.notna(c_val) or pd.notna(j_val):
        field_name = row.iloc[0]
        print(f"Field: {field_name}")
        print(f"  Col B (Segment): {b_val}")
        print(f"  Col C (Constant): {c_val}")
        print(f"  Col J (Logic): {j_val}")
        print("-" * 30)
        count += 1
        if count >= 10:
            break

print(f"\nTotal rows checked: {count}")
