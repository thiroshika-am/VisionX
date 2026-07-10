"""
VisionX — Generate PDF-ready HTML with embedded diagrams.
Run this script:  python docs/generate_pdf.py

It will create docs/visionx_diagrams.html and open it in your browser.
Then press Ctrl+P → "Save as PDF".
"""

import base64, os, webbrowser, shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
BRAIN_DIR = os.path.join(
    os.path.expanduser("~"),
    ".gemini", "antigravity-ide", "brain",
    "b1abc991-b1fe-43a3-86bc-c4c86697782f",
)

# --- Locate images (try brain dir first, then docs/) ---
def find_image(pattern, fallback_name):
    # Check brain dir
    if os.path.isdir(BRAIN_DIR):
        for f in os.listdir(BRAIN_DIR):
            if pattern in f and f.endswith(".png"):
                return os.path.join(BRAIN_DIR, f)
    # Check docs dir
    local = os.path.join(SCRIPT_DIR, fallback_name)
    if os.path.exists(local):
        return local
    return None

block_img_path = find_image("block_diagram", "visionx_block_diagram.png")
flow_img_path  = find_image("flow_chart", "visionx_flow_chart.png")

if not block_img_path or not flow_img_path:
    print("ERROR: Could not find diagram images.")
    print(f"  Looked in: {BRAIN_DIR}")
    print(f"  And in:    {SCRIPT_DIR}")
    print()
    print("Please make sure the images exist. You can copy them manually:")
    print(f"  Block diagram expected: visionx_block_diagram*.png")
    print(f"  Flow chart expected:    visionx_flow_chart*.png")
    exit(1)

# Also copy images to docs/ for future use
for src, name in [(block_img_path, "visionx_block_diagram.png"),
                   (flow_img_path, "visionx_flow_chart.png")]:
    dst = os.path.join(SCRIPT_DIR, name)
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
        print(f"Copied: {name}")

def to_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

b64_block = to_b64(block_img_path)
b64_flow  = to_b64(flow_img_path)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>VisionX — System Architecture & Working Flow</title>
<style>
  @page {{ margin: 1.5cm; }}
  body {{
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    color: #333; margin: 0 auto; max-width: 900px; padding: 2rem;
    background: #fff;
  }}
  h1 {{ text-align: center; font-size: 2rem; color: #2c3e50; margin-bottom: 0.3rem; }}
  .subtitle {{ text-align: center; color: #777; margin-bottom: 2rem; }}
  h2 {{ color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 0.4rem; }}
  .diagram {{ text-align: center; margin: 1.5rem 0; }}
  .diagram img {{ max-width: 100%; height: auto; border: 1px solid #eee; border-radius: 6px; }}
  .print-btn {{
    display: block; width: 220px; margin: 1.5rem auto; padding: 12px 24px;
    background: #007bff; color: #fff; border: none; border-radius: 6px;
    font-size: 1.1rem; cursor: pointer; text-align: center;
  }}
  .print-btn:hover {{ background: #0056b3; }}
  .page-break {{ page-break-before: always; }}
  @media print {{
    .print-btn, .no-print {{ display: none !important; }}
  }}
</style>
</head>
<body>

<h1>VisionX — AI Wearable Assistant</h1>
<p class="subtitle">System Architecture & Working Flow Documentation</p>

<button class="print-btn no-print" onclick="window.print()">⬇ Save as PDF (Ctrl+P)</button>

<h2>1. System Block Diagram</h2>
<p>High-level view of all hardware and software components and their data-flow connections.</p>
<div class="diagram">
  <img src="data:image/png;base64,{b64_block}" alt="VisionX System Architecture Block Diagram">
</div>

<div class="page-break"></div>

<h2>2. Working Flow Chart</h2>
<p>The real-time processing pipeline — from frame capture through AI processing to user feedback.</p>
<div class="diagram">
  <img src="data:image/png;base64,{b64_flow}" alt="VisionX Working Flow Chart">
</div>

</body>
</html>"""

out_path = os.path.join(SCRIPT_DIR, "visionx_diagrams.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\\n✅ Created: {out_path}")
print("Opening in your default browser...")
webbrowser.open("file:///" + out_path.replace("\\\\", "/"))
print("\\nPress Ctrl+P in the browser → 'Save as PDF' to export!")
