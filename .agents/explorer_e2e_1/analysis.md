# E2E Testing Strategy Analysis & Recommendations

**Author**: Explorer 1  
**Date**: 2026-06-24  
**Subject**: Strategy for `verify_theme.py` in NexusAI E2E Testing  

---

## 1. Observation
Based on a read-only inspection of the NexusAI codebase:
* **CSS Location**: The primary stylesheet overrides are in `public/stylesheet.css` (viewed 651 lines).
  * Lines 12-31 define CSS variables, including `--nexus-cyan: #00d4ff;` and `--nexus-violet: #7c3aed;`.
  * Lines 58-67 style the sidebar container (`[class*="sidebar"]`, etc.) with `backdrop-filter: blur(24px) saturate(1.6) !important;`.
  * Currently, there are **no overrides** for `.MuiDrawer-paper` or specific z-index/padding overlap controls in `public/stylesheet.css` (verified by complete scan of the file).
* **Theme JSON Location**: Theme configurations are in `public/theme.json` (viewed 33 lines), defining dark and light theme properties.
* **App Entry Point**: The main application file is `app.py` (viewed 1273 lines), which initiates a Chainlit/FastAPI instance.
* **Execution Environment**: The OS is Windows (`powershell` shell), meaning process management during async server execution needs to handle Windows-specific process tree structures.

---

## 2. Logic Chain
1. **CSS Variable Checks**:
   * We must verify that critical theme colors (`--nexus-cyan`, `--nexus-violet`) and glass styling (`backdrop-filter`) are present in `public/stylesheet.css`.
   * Since CSS files can contain comments and whitespace variations, a robust strategy must strip comments before matching properties to avoid false positives or negatives.
   * Testing for `.MuiDrawer-paper` overrides must fail currently because no such overrides exist in `public/stylesheet.css` yet. The test script must act as a contract that enforces their presence for the implementation agent (Milestone 3).

2. **Asynchronous Server Control**:
   * Starting `chainlit run app.py` asynchronously via Python's `subprocess.Popen` is required.
   * On Windows, launching `chainlit` via subprocess often creates a wrapper process that spawns the actual python process running the web server. Simply calling `process.terminate()` on the parent process will leave the child process running, keeping port 8000 bound.
   * Therefore, process tree termination using Windows `taskkill /F /T /PID <pid>` is required in the cleanup stage (`finally` block) to ensure port 8000 is always freed.
   * Health checking should use python's standard library `urllib.request` to poll `http://localhost:8000` periodically (e.g., every 0.5 seconds with a timeout of 15 seconds) to handle server startup lag.

---

## 3. Caveats
* **Port Availability**: If port 8000 is already in use by another application before the test starts, the server launch will fail. The script should verify that port 8000 is free before starting the process.
* **Standard Library vs. External Libraries**: We recommend writing `verify_theme.py` using only the Python standard library (`re`, `subprocess`, `urllib.request`, `sys`, `time`, `socket`) to avoid external library dependencies like `tinycss2` or `requests` that might not be installed in the runtime environment.
* **Windows Execution Policy**: Invoking the command `chainlit` directly might fail if the virtual environment is not activated or if the executable is not in the system PATH. The test runner should support executing via shell or using python's executable module path if possible.

---

## 4. Conclusion & Recommended Strategy
We recommend the following design for the `verify_theme.py` test script:

### A. CSS AST / Parser Strategy
1. **Comment Stripping**: Read `public/stylesheet.css` and use a regex to strip comments:
   ```python
   css_content = re.sub(r'/\*.*?\*/', '', css_content, flags=re.DOTALL)
   ```
2. **CSS Variable Assertions**: Verify that the exact colors and blur settings are present:
   - `--nexus-cyan`: `re.search(r'--nexus-cyan\s*:\s*[^;]+;', css_content)`
   - `--nexus-violet`: `re.search(r'--nexus-violet\s*:\s*[^;]+;', css_content)`
   - `backdrop-filter`: Check for backdrop-filter presence inside sidebar selectors.
3. **Selector Overrides Verification**: Define a state machine or regex to locate the rule block for `.MuiDrawer-paper` (or `[class*="MuiDrawer-paper"]`) and assert that it contains properties for `z-index` and `padding` (or `margin`/`width` spacing controls).
   - *Example Regex*:
     ```python
     drawer_block = re.search(r'(?:\.MuiDrawer-paper|\[class\*=["\']MuiDrawer-paper["\']\])[^{]*\{([^}]+)\}', css_content)
     if drawer_block:
         block_content = drawer_block.group(1)
         assert "z-index" in block_content
         assert "padding" in block_content or "margin" in block_content
     ```

### B. Async Server & Health Check Strategy
1. **Port Check**: Before starting, verify port 8000 is not in use:
   ```python
   import socket
   with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
       port_in_use = (s.connect_ex(('127.0.0.1', 8000)) == 0)
   ```
2. **Server Launch**: Run the server asynchronously using `subprocess.Popen`:
   ```python
   # Windows-specific: use shell=True to run chainlit through shell wrapper if needed
   cmd = ["chainlit", "run", "app.py", "--port", "8000"]
   process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
   ```
3. **Health Check Loop**: Poll `http://localhost:8000` until successful or timeout:
   ```python
   import urllib.request
   import time
   
   start_time = time.time()
   server_ready = False
   while time.time() - start_time < 15:
       try:
           with urllib.request.urlopen("http://localhost:8000", timeout=2) as response:
               if response.status == 200:
                   server_ready = True
                   break
       except Exception:
           time.sleep(0.5)
   ```
4. **Graceful Cleanup (Windows-Robust)**: Ensure the process is killed using `taskkill` in a `finally` block:
   ```python
   try:
       # Run test assertions here...
   finally:
       if process:
           # Terminate process tree on Windows
           subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
   ```

---

## 5. Verification Method
To verify that this E2E strategy works:
1. Create a prototype of `verify_theme.py` incorporating these mechanisms.
2. Run `python verify_theme.py`.
3. Expected Behavior:
   - The CSS checks should fail on the drawer override assertion (since `.MuiDrawer-paper` is not yet modified in `public/stylesheet.css`).
   - The server launch and health check should pass (verifying the server responds to port 8000).
   - The server should terminate completely, leaving no orphan processes on port 8000 (verifiable by running `netstat -ano | findstr 8000` which should return empty after the script terminates).
