# Handoff Report - Explorer 1 E2E Testing Strategy

## 1. Observation
Based on a read-only inspection of the NexusAI codebase:
* **CSS Location**: The primary stylesheet overrides are in `public/stylesheet.css`.
  * Lines 12-31 define CSS variables, including `--nexus-cyan: #00d4ff;` and `--nexus-violet: #7c3aed;`.
  * Lines 58-67 style the sidebar container (`[class*="sidebar"]`, etc.) with `backdrop-filter: blur(24px) saturate(1.6) !important;`.
  * Currently, there are **no overrides** for `.MuiDrawer-paper` or specific z-index/padding overlap controls in `public/stylesheet.css`.
* **Theme JSON Location**: Theme configurations are in `public/theme.json`, defining dark and light theme properties.
* **App Entry Point**: The main application file is `app.py`, which initiates a Chainlit/FastAPI instance.
* **Execution Environment**: The OS is Windows (`powershell` shell), meaning process management during async server execution needs to handle Windows-specific process tree structures.

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

## 3. Caveats
* **Port Availability**: If port 8000 is already in use by another application before the test starts, the server launch will fail. The script should verify that port 8000 is free before starting the process.
* **Standard Library vs. External Libraries**: We recommend writing `verify_theme.py` using only the Python standard library (`re`, `subprocess`, `urllib.request`, `sys`, `time`, `socket`) to avoid external library dependencies like `tinycss2` or `requests` that might not be installed in the runtime environment.
* **Windows Execution Policy**: Invoking the command `chainlit` directly might fail if the virtual environment is not activated or if the executable is not in the system PATH. The test runner should support executing via shell or using python's executable module path if possible.

## 4. Conclusion
We recommend the following design for the `verify_theme.py` test script:
1. **CSS AST / Parser Strategy**: Read `public/stylesheet.css`, strip comments using regex, and assert variables (`--nexus-cyan`, `--nexus-violet`), presence of `backdrop-filter`, and selector blocks for `.MuiDrawer-paper` (asserting z-index and padding/margin properties exist).
2. **Async Server & Health Check Strategy**: Check if port 8000 is free, launch the server using `subprocess.Popen(..., shell=True)` (or direct invocation), poll `http://localhost:8000` using `urllib.request.urlopen` with a 15-second timeout, and guarantee process tree cleanup in a `finally` block using `taskkill /F /T /PID <pid>`.

## 5. Verification Method
To verify that this E2E strategy works:
1. Create a prototype of `verify_theme.py` incorporating these mechanisms.
2. Run `python verify_theme.py`.
3. Expected Behavior:
   - The CSS checks should fail on the drawer override assertion (since `.MuiDrawer-paper` is not yet modified in `public/stylesheet.css`).
   - The server launch and health check should pass (verifying the server responds to port 8000).
   - The server should terminate completely, leaving no orphan processes on port 8000.
