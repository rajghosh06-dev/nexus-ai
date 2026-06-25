# E2E Test Strategy Analysis — verify_theme.py

This analysis outlines a robust strategy for implementing the E2E test runner script `verify_theme.py` as specified in the project requirements, architecture guidelines (`PROJECT.md`, `TEST_INFRA.md`), and the E2E track scope (`SCOPE.md`).

---

## 1. Strategy Overview

The testing philosophy is **opaque-box and requirement-driven**. The verification runner `verify_theme.py` will have two main responsibilities:
1. **CSS Static Analysis & AST-like Checks**: Parses `public/stylesheet.css` to confirm that required design systems, variables, glassmorphism filters, and layout fixes (such as drawer overrides) are correctly defined.
2. **Active Runtime Health Checks**: Launches the Chainlit application asynchronously, polls the health endpoint to confirm successful startup and stylesheet loading, and clean-terminates the server process tree.

---

## 2. Part 1: CSS Parsing & Assertion Strategy

To ensure zero-dependency execution and maximum portability across python environments, the CSS parser will utilize Python's standard `re` module rather than external packages like `tinycss2`. It will perform comments-stripping, tokenization of rulesets, and value assertions.

### A. Regex-based Ruleset Extraction
The parser should strip out comments and map selectors to dictionary properties:

```python
import re

def parse_css_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Strip CSS Comments
    content_clean = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # 2. Extract Selector Blocks: selector { declaration-block }
    blocks = re.findall(r'([^{]+)\{([^}]+)\}', content_clean)
    
    rules = {}
    for selector, decs in blocks:
        selector = selector.strip()
        selector_norm = re.sub(r'\s+', ' ', selector) # Normalize whitespaces
        
        properties = {}
        for dec in decs.split(';'):
            dec = dec.strip()
            if not dec or ':' not in dec:
                continue
            prop_name, prop_val = dec.split(':', 1)
            properties[prop_name.strip()] = prop_val.strip()
            
        rules[selector_norm] = properties
    return rules
```

### B. Core Assertions to Run

1. **CSS Variable Checks**:
   - Verify that `:root` defines `--nexus-cyan` (color value `#00d4ff` or equivalent gradient components).
   - Verify that `:root` defines `--nexus-violet` (color value `#7c3aed`).
   - Validate color formats (e.g. hex codes matching `#[a-fA-F0-9]{3,8}` or `rgba(...)` formats).

2. **Backdrop Filter Checks**:
   - Verify that `backdrop-filter: blur(...)` and/or `-webkit-backdrop-filter: blur(...)` properties are active on key UI panels (such as sidebar containers, user/assistant message bubbles, input footers).
   - Search the parsed rules to ensure at least one active selector (e.g. `[class*="sidebar"]`, `[class*="input-area"]`, or `.MuiDrawer-paper`) incorporates a `backdrop-filter` property with a valid `blur` statement.

3. **Sidebar Overlap Overrides**:
   - To resolve **Milestone 3 (Sidebar Overlap Fix)**, the stylesheet must override `.MuiDrawer-paper` or equivalent Material UI classes.
   - The test script must locate any rules matching `.MuiDrawer-paper`, `[class*="MuiDrawer-paper"]`, or similar, and assert:
     - **`z-index`** override exists (e.g., `z-index` property with `!important` or a high value such as `1200` to prevent background overlap).
     - **`padding` or `margin`** properties (such as `padding-left`/`padding-right` or `margin-left`/`margin-right`) are explicitly set to prevent layout collision with the chat area content wrapper.

---

## 3. Part 2: Asynchronous Server Launch & Termination Strategy

Testing the real-world server startup requires launching `app.py` under the same Python interpreter using an asynchronous subprocess, making HTTP requests, and executing a clean kill-tree command to prevent port-binding exhaustion.

### A. Environment-Aware Execution
To avoid environmental configuration errors (such as missing PATH entries), the script should execute Chainlit using `sys.executable` (referencing the current active virtual environment/Conda executable) combined with the `-m chainlit` option.

- **Launch Command**: `[sys.executable, "-m", "chainlit", "run", "app.py", "--port", "8000", "--headless"]`
- **Environment**: Inherit from `os.environ.copy()` to pass API keys (`GROQ_API_KEY`, `GEMINI_API_KEY`) and include `CHAINLIT_PORT="8000"`.

### B. Health Poll Loop (Standard Library Only)
Use standard Python `urllib.request` to poll `http://localhost:8000` with retry delays and a fixed timeout (e.g. 30 seconds). This keeps the script fully portable.

```python
import time
import urllib.request
import urllib.error

def verify_server_health(url="http://localhost:8000", timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = urllib.request.urlopen(url, timeout=3)
            if response.status == 200:
                html = response.read().decode('utf-8')
                if "<html" in html.lower() or "chainlit" in html.lower():
                    return True
        except Exception:
            # Server not initialized yet, wait and retry
            time.sleep(1.5)
    return False
```

### C. Graceful Process Tree Termination (Windows-Friendly)
On Windows, when running `chainlit run`, the python runner spawns child processes (like `uvicorn`). Simply calling `process.terminate()` on the parent process leaves orphaned child processes running, keeping port 8000 bound and blocking future test runs.
- **Windows Solution**: Use the `taskkill` utility with `/F` (force) and `/T` (tree) flags on the subprocess PID.
- **Unix Solution**: Fall back to standard `SIGTERM` / `SIGKILL` signals.

```python
import os
import signal
import subprocess

def terminate_process(process):
    if process.poll() is not None:
        return # Already terminated
        
    if os.name == 'nt':
        # Forcefully terminate process and all child subprocesses on Windows
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
    else:
        # Standard Unix termination
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
```

---

## 4. Proposed verify_theme.py Architecture

Below is the complete architectural layout of the proposed `verify_theme.py` testing script:

```python
#!/usr/bin/env python
"""
verify_theme.py
End-to-End Test Suite for NexusAI Liquid Glass Frost Theme.
Parses public/stylesheet.css and runs runtime app startup validation.
"""

import os
import sys
import re
import time
import subprocess
import urllib.request

CSS_PATH = os.path.join(os.path.dirname(__file__), "public", "stylesheet.css")

def log_success(msg):
    print(f"\033[92m[✓] SUCCESS: {msg}\033[0m")

def log_fail(msg):
    print(f"\033[91m[✗] FAILED: {msg}\033[0m", file=sys.stderr)

def parse_css(filepath):
    # (Implementation as described in Section 2A)
    ...

def test_css_variables_and_rules():
    print("[*] Running CSS Static Assertions...")
    if not os.path.exists(CSS_PATH):
        log_fail(f"Stylesheet not found at {CSS_PATH}")
        sys.exit(1)
        
    rules = parse_css(CSS_PATH)
    
    # 1. Check for color variables in :root
    root_props = rules.get(":root", {})
    cyan = root_props.get("--nexus-cyan")
    violet = root_props.get("--nexus-violet")
    
    if not cyan or not re.match(r'#[a-fA-F0-9]{3,8}|rgba?\(.*\)', cyan):
        log_fail(f"--nexus-cyan variable is invalid or missing. Value: {cyan}")
        sys.exit(1)
    log_success(f"Verified --nexus-cyan = {cyan}")
    
    if not violet or not re.match(r'#[a-fA-F0-9]{3,8}|rgba?\(.*\)', violet):
        log_fail(f"--nexus-violet variable is invalid or missing. Value: {violet}")
        sys.exit(1)
    log_success(f"Verified --nexus-violet = {violet}")
    
    # 2. Check for backdrop-filter presence
    has_blur = False
    for selector, props in rules.items():
        if 'backdrop-filter' in props or '-webkit-backdrop-filter' in props:
            val = props.get('backdrop-filter') or props.get('-webkit-backdrop-filter')
            if 'blur' in val:
                has_blur = True
                break
    if not has_blur:
        log_fail("No blur backdrop-filter found in stylesheet.css")
        sys.exit(1)
    log_success("Verified glassmorphism backdrop-filter blur is declared.")
    
    # 3. Check for MuiDrawer-paper sidebar overrides
    drawer_key = None
    for selector in rules.keys():
        if "MuiDrawer-paper" in selector:
            drawer_key = selector
            break
            
    if not drawer_key:
        # Check if z-index is set in general sidebar selector if MuiDrawer is not yet implemented
        log_fail("MuiDrawer-paper selector overrides not found in stylesheet.css")
        sys.exit(1)
        
    drawer_props = rules[drawer_key]
    z_index = drawer_props.get("z-index")
    padding = drawer_props.get("padding") or drawer_props.get("padding-left") or drawer_props.get("padding-right")
    margin = drawer_props.get("margin") or drawer_props.get("margin-left") or drawer_props.get("margin-right")
    
    if not z_index:
        log_fail(f"MuiDrawer-paper selector exists but is missing 'z-index' property.")
        sys.exit(1)
    if not padding and not margin:
        log_fail(f"MuiDrawer-paper override must declare padding or margin parameters to prevent layout overlap.")
        sys.exit(1)
        
    log_success(f"Verified MuiDrawer-paper layout overrides: z-index={z_index}, spacing properties validated.")
    print("[*] CSS assertions completed successfully.\n")

def test_server_runtime():
    print("[*] Starting asynchronous Chainlit app runtime check...")
    env = os.environ.copy()
    env["CHAINLIT_PORT"] = "8000"
    
    cmd = [sys.executable, "-m", "chainlit", "run", "app.py", "--port", "8000", "--headless"]
    
    # Start subprocess
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True
    )
    
    try:
        # Check server health
        print("[*] Polling http://localhost:8000/ for health check (max 30s)...")
        if verify_server_health(timeout=30):
            log_success("Chainlit server responsive on port 8000. UI served successfully.")
        else:
            log_fail("Chainlit server failed to start or respond on port 8000 within 30 seconds.")
            # Print stderr if process exited
            if process.poll() is not None:
                stderr_log = process.stderr.read()
                print(f"[!] Server Exit Stderr Log:\n{stderr_log}", file=sys.stderr)
            sys.exit(1)
    finally:
        print("[*] Gracefully terminating Chainlit server process tree...")
        terminate_process(process)
        log_success("Chainlit server terminated cleanly.")

def main():
    test_css_variables_and_rules()
    test_server_runtime()
    log_success("ALL E2E TESTING ASSERIONS PASSED.")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

This strategy satisfies all constraints, ensures robust verification of theme requirements, addresses Windows process group challenges, and adheres to the specifications in `TEST_INFRA.md`.
