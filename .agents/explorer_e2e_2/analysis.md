# E2E Theme and Process Verification Strategy

This document outlines a recommended E2E testing strategy for verifying the **Liquid Glass Frost** theme configuration, sidebar overlap overrides, and the operational health of the Chainlit application. This strategy is tailored for implementation in a zero-dependency Python script, `verify_theme.py`, running in a Windows environment.

---

## 1. Executive Summary
The E2E testing framework is designed to validate the visual assets and process health of the NexusAI application. The test script `verify_theme.py` must run as a standalone Python script, executing statically against stylesheet assets and dynamically against the live Chainlit server. 
It guarantees:
- **Style compliance**: The "Liquid Glass Frost" CSS variables, glassmorphism filters, scrollbars, code blocks, and layout overrides are correctly defined.
- **Sidebar isolation**: The Material UI drawer (`.MuiDrawer-paper`) or equivalent sidebar layout structure has proper overrides (`z-index` and `padding` / `margin`) to prevent chat panel overlap.
- **Process stability**: The Chainlit application launches correctly on port 8000, responds to health probes with valid HTML payloads, and terminates cleanly without leaving zombie processes.

---

## 2. CSS Analysis and Extraction Strategy
Because python environments may not have CSS parsing libraries installed (such as `tinycss2` or `cssutils`), we recommend a zero-dependency, regex-based CSS parser built using Python's standard `re` library. 

### A. CSS Parser Implementation
The parser must:
1. Strip CSS multi-line comments (`/* ... */`) to prevent false matches.
2. Group CSS rules into selectors and properties using a regular expression that handles formatting variations (whitespaces, line breaks).
3. Populate a Python dictionary mapping selectors to their declared key-value properties.

**Regex Pattern for CSS Rules:**
```python
r'([^{]+)\s*\{\s*([^}]+)\s*\}'
```

### B. Specific Styling Assertions
The test script must enforce the following assertions:

1. **Liquid Glass Frost Theme Variables**:
   - Locate the `:root` selector rule.
   - Assert that `--nexus-cyan` is defined. Verify its value is a valid hex color code (e.g. `#00d4ff`) or rgb/rgba expression.
   - Assert that `--nexus-violet` is defined. Verify its value is a valid hex color code (e.g. `#7c3aed`) or rgb/rgba expression.

2. **Glassmorphism Backdrop Filters**:
   - Assert that `backdrop-filter` (or `-webkit-backdrop-filter`) is declared on key layout panels.
   - Verify that it uses the `blur(...)` function (e.g., `blur(24px) saturate(1.6)` on the sidebar or `blur(12px)` on message bubbles).

3. **Sidebar Overlap Prevention (`.MuiDrawer-paper` / Layout Selectors)**:
   - Identify the selector matching `.MuiDrawer-paper` (the Material UI container class used by Chainlit's sidebar drawer).
   - Assert that this rule contains:
     - `z-index` declaration (to ensure it sits at the correct layering height relative to other components).
     - `padding` or `margin` properties (e.g. `padding-top` or `padding-right` overrides) that isolate the drawer and prevent it from overlapping the chat workspace area.
   - If the selector `.MuiDrawer-paper` is missing, the test must raise an assertion error.

4. **Scrollbars & Code Blocks**:
   - Verify selectors for `::-webkit-scrollbar-thumb` and `::-webkit-scrollbar-track` are defined.
   - Verify that `pre` or `[class*="code-block"]` rules enforce monospace styling using `'JetBrains Mono'`.

---

## 3. Server Launch and Health Verification Strategy

Orchestrating a Python web server process dynamically and safely requires a robust process management loop, especially under Windows.

### A. Pre-Flight Port Check
Before spawning Chainlit, the script must verify if port 8000 is already in use by another process. This prevents silent execution failures or connecting to a stale, previously orphaned process.
- **Mechanism**: Attempt to bind a `socket.socket` to `('localhost', 8000)`. If connection succeeds, the port is active, and the test must alert the user or kill the conflicting process.

### B. Asynchronous Invocation
To launch the server without blocking the main test script thread:
- **Windows Command Safety**: Instead of running the raw command `chainlit run app.py --port 8000`, run it via python's module entry point:
  ```python
  import sys
  cmd = [sys.executable, "-m", "chainlit", "run", "app.py", "--port", "8000"]
  ```
- **Why?**:
  1. It guarantees the process uses the exact same virtual environment (`.venv`) as the running test script.
  2. Spawning the Python interpreter directly allows `subprocess.Popen` to manage the process tree cleanly without needing `shell=True`. On Windows, `shell=True` spawns a command shell wrapper (`cmd.exe`), which traps `terminate()` signals and leaves the child Python server running as an orphan on port 8000.

### C. Health Check and Polling Loop
Once spawned, the server takes several seconds to compile assets and bind to the port. The script must implement a polling loop:
- **Timeout**: 30 seconds.
- **Interval**: 1 second.
- **Probe Endpoint**: `http://localhost:8000`
- **Verification**:
  - Perform an HTTP GET request using `urllib.request.urlopen`.
  - Assert that the response returns status code `200`.
  - Check that the returned HTML content contains standard Chainlit elements (like `<div id="root">`) or custom NexusAI references to ensure it is not serving a generic error page.
  - If the subprocess ends prematurely (`process.poll() is not None`), capture stdout/stderr and fail the test immediately.

### D. Graceful Termination
Once the health check is completed (successfully or with failures), the server must be stopped cleanly:
- Call `process.terminate()`.
- Wait up to 5 seconds for the process to exit using `process.wait(timeout=5)`.
- If the process fails to exit, call `process.kill()` to force-terminate.
- Perform a post-test port verification to ensure port 8000 is successfully unbound.

---

## 4. Implementation Blueprint (verify_theme.py)

Here is a recommended zero-dependency Python blueprint for `verify_theme.py`.

```python
"""
verify_theme.py
E2E testing script for NexusAI.
Validates Liquid Glass Frost theme styling and launches Chainlit app server health check.
Exit code: 0 on success, non-zero on failure.
"""

import os
import sys
import re
import socket
import subprocess
import time
import urllib.request
import urllib.error

# Paths
STYLESHEET_PATH = os.path.join("public", "stylesheet.css")
THEME_JSON_PATH = os.path.join("public", "theme.json")
PORT = 8000
SERVER_URL = f"http://localhost:{PORT}"

def log(msg):
    print(f"[TEST RUNNER] {msg}")

# ============================================================
# PART 1: CSS PARSING & STATIC STYLE VERIFICATION
# ============================================================

def parse_css(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Stylesheet not found at: {file_path}")
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Strip comments to prevent false matches
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # Extract selectors and declaration blocks
    rule_pattern = re.compile(r'([^{]+)\s*\{\s*([^}]+)\s*\}')
    parsed_rules = []
    
    for match in rule_pattern.finditer(content):
        selectors_str = match.group(1).strip()
        properties_str = match.group(2).strip()
        
        # Split selectors (to support comma-separated lists)
        selectors = [s.strip() for s in selectors_str.split(',') if s.strip()]
        
        properties = {}
        for prop in properties_str.split(';'):
            if not prop.strip() or ':' not in prop:
                continue
            name, val = prop.split(':', 1)
            properties[name.strip().lower()] = val.strip()
            
        parsed_rules.append({
            "selectors": selectors,
            "properties": properties
        })
        
    return parsed_rules

def verify_stylesheet():
    log("Verifying stylesheet.css properties...")
    rules = parse_css(STYLESHEET_PATH)
    
    # Extract :root variables
    root_vars = {}
    for rule in rules:
        if ":root" in rule["selectors"]:
            root_vars.update(rule["properties"])
            
    # Check variables
    assert "--nexus-cyan" in root_vars, "CSS Variable --nexus-cyan is missing in :root!"
    assert "--nexus-violet" in root_vars, "CSS Variable --nexus-violet is missing in :root!"
    log(f"-> Found variables: --nexus-cyan={root_vars['--nexus-cyan']}, --nexus-violet={root_vars['--nexus-violet']}")
    
    # Check glassmorphism filter presence
    has_blur = False
    for rule in rules:
        props = rule["properties"]
        if "backdrop-filter" in props or "-webkit-backdrop-filter" in props:
            filt = props.get("backdrop-filter") or props.get("-webkit-backdrop-filter")
            if "blur" in filt:
                has_blur = True
                break
    assert has_blur, "No 'backdrop-filter: blur(...)' rule found in stylesheet.css!"
    log("-> Glassmorphism backdrop-filter presence verified.")
    
    # Check sidebar layout overlap overrides (.MuiDrawer-paper or equivalent)
    drawer_rule = None
    for rule in rules:
        # Check if '.MuiDrawer-paper' is explicitly overridden
        if any(".MuiDrawer-paper" in sel for sel in rule["selectors"]):
            drawer_rule = rule
            break
            
    assert drawer_rule is not None, "CSS override for '.MuiDrawer-paper' is missing!"
    
    props = drawer_rule["properties"]
    assert "z-index" in props, "'.MuiDrawer-paper' override is missing 'z-index' property!"
    # Ensure it defines padding or margin to manage spacing
    has_layout_spacing = "padding" in props or "margin" in props or any(p.startswith("padding-") or p.startswith("margin-") for p in props)
    assert has_layout_spacing, "'.MuiDrawer-paper' override is missing spacing property (padding/margin)!"
    
    log(f"-> Verified '.MuiDrawer-paper' overrides: z-index={props['z-index']}")
    log("[SUCCESS] Static CSS validation passed.")

# ============================================================
# PART 2: DYNAMIC PROCESS ORCHESTRATION & HEALTH CHECK
# ============================================================

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def run_server_health_check():
    log(f"Checking if port {PORT} is already bound...")
    if is_port_in_use(PORT):
        raise RuntimeError(f"Port {PORT} is already in use. Clean up the process before running the test.")
        
    log("Starting Chainlit server asynchronously...")
    cmd = [sys.executable, "-m", "chainlit", "run", "app.py", "--port", str(PORT)]
    
    # Spawn process using direct environment python wrapper
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    success = False
    start_time = time.time()
    timeout = 30
    
    try:
        log("Waiting for server to spin up and respond...")
        while time.time() - start_time < timeout:
            # Check if server process terminated prematurely
            ret = process.poll()
            if ret is not None:
                # Capture stderr for logs
                _, stderr = process.communicate()
                raise RuntimeError(f"Server crashed with exit code {ret}. Stderr: {stderr}")
                
            try:
                # Probe http://localhost:8000
                req = urllib.request.Request(SERVER_URL, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=2) as response:
                    if response.status == 200:
                        content = response.read().decode('utf-8')
                        # Confirm index page structure
                        if "root" in content or "chainlit" in content.lower():
                            log(f"Server is healthy! Responded 200 OK after {int(time.time() - start_time)} seconds.")
                            success = True
                            break
            except (urllib.error.URLError, ConnectionResetError):
                # Server is starting up
                time.sleep(1)
                
        if not success:
            raise TimeoutError("Chainlit server failed to respond within the 30 second timeout.")
            
    finally:
        log("Terminating Chainlit server process...")
        process.terminate()
        try:
            process.wait(timeout=5)
            log("Server exited cleanly.")
        except subprocess.TimeoutExpired:
            log("Server did not exit within timeout. Killing forceably...")
            process.kill()
            process.wait()
            log("Server process terminated via SIGKILL.")

# ============================================================
# MAIN RUNNER
# ============================================================

def main():
    try:
        verify_stylesheet()
        run_server_health_check()
        log("All E2E checks passed successfully.")
        sys.exit(0)
    except Exception as e:
        log(f"[TEST FAILED] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

---

## 5. Traceability Matrix

| Requirement | Source File / ID | Test Strategy |
|---|---|---|
| `--nexus-cyan`, `--nexus-violet` definitions | `PROJECT.md` line 21, `TEST_INFRA.md` line 16 | Extract `:root` properties and assert presence of variable names. |
| Glass frost backgrounds (`backdrop-filter`) | `PROJECT.md` line 22, `TEST_INFRA.md` line 16 | Scan CSS properties for occurrences of `backdrop-filter: blur(...)`. |
| Sidebar Overlap Prevention | `PROJECT.md` line 20, `TEST_INFRA.md` line 23 | Match `.MuiDrawer-paper` selector and assert definitions for `z-index` and `padding` / `margin`. |
| Server Responsive Health Check | `SCOPE.md` line 13, `TEST_INFRA.md` line 34 | Perform async process spawn, poll `http://localhost:8000`, verify `200 OK` HTML structure. |
| Safe Process Cleanup (Windows-specific) | `SCOPE.md` line 13, `TEST_INFRA.md` line 34 | Spawn using `sys.executable` to prevent shell-isolated child processes, call `terminate()` and `kill()`. |
