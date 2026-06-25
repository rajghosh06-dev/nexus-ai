## 2026-06-24T13:51:23Z

You are the Worker. Your working directory is E:\RAJ-WORK\PROJECT\nexus-ai\.agents\worker_e2e.

Task:
Implement the E2E verification script `verify_theme.py` in the project root directory E:\RAJ-WORK\PROJECT\nexus-ai.

The `verify_theme.py` script must:
1. Be written in Python with no external dependencies (using only the standard library: `os`, `sys`, `re`, `time`, `socket`, `subprocess`, `urllib.request`, `urllib.error`).
2. Read `public/stylesheet.css` and parse it (safely stripping CSS comments `/* ... */` first).
3. Validate that `public/stylesheet.css` defines color variables `--nexus-cyan` and `--nexus-violet`.
4. Validate that a CSS override block for `.MuiDrawer-paper` (or `[class*="MuiDrawer-paper"]`) exists and specifies `z-index` and `padding` (or `margin`) properties to fix sidebar overlaps.
5. Validate that `backdrop-filter` (or `-webkit-backdrop-filter`) with a `blur(...)` value is declared on relevant panel(s).
6. Programmatically launch the server using `chainlit run app.py` asynchronously on port 8000 (running through `sys.executable -m chainlit run app.py --port 8000`). Perform a pre-flight port check to ensure port 8000 is not already occupied.
7. Poll `http://localhost:8000` until it returns status 200 OK (allow a timeout of 20 seconds).
8. Ensure the spawned server process and all its child processes are gracefully terminated in a `finally` block using `taskkill /F /T /PID <pid>` on Windows (`os.name == 'nt'`), and standard process termination (`process.terminate()` / `process.kill()`) on other platforms.
9. Provide clear CLI logging and exit with 0 on success, or a non-zero code on failure.

Run the test suite on the current codebase to verify that it correctly reports the missing CSS overrides (since they haven't been implemented yet) but the server startup/shutdown check passes.

Write a handoff report in E:\RAJ-WORK\PROJECT\nexus-ai\.agents\worker_e2e\handoff.md detailing the script structure, how to execute it, and the results of your local execution.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
