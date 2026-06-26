import sys
import os

# Add project root to sys.path to allow resolving tests module correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import subprocess
import time
import requests

def cleanup_port(port):
    print(f"[Runner] Checking if port {port} is in use...")
    if sys.platform.startswith('win'):
        try:
            res = subprocess.run("netstat -ano", capture_output=True, text=True, shell=True)
            pids_to_kill = set()
            for line in res.stdout.splitlines():
                if "LISTENING" in line and f":{port}" in line:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        local_addr = parts[1]
                        if local_addr.endswith(f":{port}"):
                            pids_to_kill.add(pid)
            for pid in pids_to_kill:
                print(f"[Runner] Windows: Killing process {pid} listening on port {port}...")
                subprocess.run(f"taskkill /F /PID {pid}", shell=True)
        except Exception as e:
            print(f"[Runner] Error cleaning up port on Windows: {e}")
    else:
        try:
            subprocess.run(f"lsof -t -i:{port} | xargs kill -9", shell=True, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"[Runner] Cross-platform fallback cleanup error: {e}")

def start_server(port, env=None):
    cmd = [
        r"C:\Users\sapna\miniconda3\envs\nexus\python.exe",
        "-u",
        "-m",
        "chainlit",
        "run",
        "app.py",
        "-h",
        "--port",
        str(port)
    ]
    run_env = os.environ.copy()
    run_env["PYTHONUNBUFFERED"] = "1"
    if env:
        run_env.update(env)
    
    print(f"[Runner] Spawning Chainlit server on port {port}...")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_file_path = os.path.join(project_root, "tests", "server.log")
    
    # Ensure tests directory exists to write log
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
    log_file = open(log_file_path, "w", encoding="utf-8")
    
    process = subprocess.Popen(
        cmd,
        env=run_env,
        stdout=log_file,
        stderr=log_file,
        cwd=project_root
    )
    return process

def wait_for_server(url, timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                print(f"[Runner] Server is up and returned status 200.")
                return True
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Server at {url} did not respond with 200 within {timeout} seconds.")

def run_all_tests():
    import unittest
    port = 8000
    url = f"http://localhost:{port}"
    
    cleanup_port(port)
    
    process = None
    try:
        process = start_server(port)
        wait_for_server(url, timeout=30)
        
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tests_dir = os.path.join(project_root, "tests")
        
        loader = unittest.TestLoader()
        suite = loader.discover(start_dir=tests_dir, pattern="test_*.py")
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        if not result.wasSuccessful():
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        print(f"[Runner] Error during test execution: {e}")
        sys.exit(1)
        
    finally:
        if process:
            print("[Runner] Stopping Chainlit server...")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("[Runner] Server process did not terminate. Killing it...")
                process.kill()
        cleanup_port(port)

if __name__ == "__main__":
    run_all_tests()
