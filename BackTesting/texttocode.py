import re
import os

# Input file
input_file = "fullcode.txt"


# Read the whole content
with open(input_file, "r", encoding="utf-8") as f:
    content = f.read()

# Pattern to detect filenames like ### filename.py ###
pattern = r"###\s*(.+\.py)\s*###"

# Split content by the pattern
matches = list(re.finditer(pattern, content))

for i, match in enumerate(matches):
    filename = match.group(1).strip()
    start = match.end()
    end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
    file_content = content[start:end].strip()
    
    # Create the file
    with open(filename, "w", encoding="utf-8") as f:
        f.write(file_content)
    
    print(f"Created file: {filename}")

print("All .py files have been created successfully!")

