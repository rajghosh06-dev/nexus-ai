#!/usr/bin/env python3
"""
E2E Verification Script for NexusAI Theme and Layout.
This script checks public/stylesheet.css validations and performs server launch/health check.
"""
import os
import sys
import re
import time
import socket
import subprocess
import urllib.request
import urllib.error

# Configuration
CSS_PATH = os.path.join("public", "stylesheet.css")
PORT = 8000
SERVER_URL = f"http://127.0.0.1:{PORT}"
TIMEOUT = 60
LOG_FILE_PATH = "server_run.log"

def log(message):
    print(f"[E2E] {message}")

def check_port_occupied(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(('127.0.0.1', port)) == 0

def clean_css_comments(css_content):
    # Remove CSS comments: /* ... */
    return re.sub(r'/\*[\s\S]*?\*/', '', css_content)

def parse_css_blocks(css_text):
    # Parse blocks into selector-body pairs, handling nesting
    rules = []
    current_selector = ""
    current_body = ""
    depth = 0
    
    i = 0
    n = len(css_text)
    while i < n:
        char = css_text[i]
        if char == '{':
            depth += 1
            if depth == 1:
                current_selector = current_selector.strip()
            else:
                current_body += char
        elif char == '}':
            depth -= 1
            if depth == 0:
                rules.append((current_selector, current_body.strip()))
                current_selector = ""
                current_body = ""
            else:
                current_body += char
        else:
            if depth == 0:
                current_selector += char
            else:
                current_body += char
        i += 1
    return rules

def extract_all_blocks(css_text):
    blocks = parse_css_blocks(css_text)
    all_blocks = []
    
    def recurse(rules_list):
        for sel, body in rules_list:
            if sel.startswith('@media'):
                nested = parse_css_blocks(body)
                recurse(nested)
            else:
                all_blocks.append((sel, body))
                
    recurse(blocks)
    return all_blocks

def validate_css():
    log(f"Reading CSS from {CSS_PATH}...")
    if not os.path.exists(CSS_PATH):
        log(f"Error: {CSS_PATH} does not exist!")
        return False, ["CSS file missing"]
        
    with open(CSS_PATH, "r", encoding="utf-8") as f:
        raw_content = f.read()
        
    clean_content = clean_css_comments(raw_content)
    
    failures = []
    
    # 1. Color variables validation
    if not re.search(r'(?<![\w-])--nexus-cyan\s*:', clean_content):
        failures.append("Missing --nexus-cyan definition in CSS")
    else:
        log("Passed: --nexus-cyan color variable is defined.")
        
    if not re.search(r'(?<![\w-])--nexus-violet\s*:', clean_content):
        failures.append("Missing --nexus-violet definition in CSS")
    else:
        log("Passed: --nexus-violet color variable is defined.")
        
    # 2. Backdrop-filter with blur validation
    # Check if backdrop-filter or -webkit-backdrop-filter with blur(...) exists
    backdrop_filter_pattern = r'(?:-webkit-)?backdrop-filter\s*:\s*[^;]*\bblur\s*\([^)]*\)'
    backdrop_filters_found = re.findall(backdrop_filter_pattern, clean_content)
    if not backdrop_filters_found:
        failures.append("Missing backdrop-filter or -webkit-backdrop-filter with blur(...) in CSS")
    else:
        log(f"Passed: Found {len(backdrop_filters_found)} backdrop-filter declarations with blur.")
        
    # 3. .MuiDrawer-paper or equivalent check
    blocks = extract_all_blocks(clean_content)
    
    drawer_blocks = []
    for selector, body in blocks:
        if '.MuiDrawer-paper' in selector or 'MuiDrawer-paper' in selector:
            drawer_blocks.append((selector, body))
            
    if not drawer_blocks:
        failures.append("Missing CSS override block for .MuiDrawer-paper or [class*='MuiDrawer-paper']")
    else:
        log(f"Found {len(drawer_blocks)} blocks matching MuiDrawer-paper selector.")
        has_z_index = False
        has_padding_or_margin = False
        for selector, body in drawer_blocks:
            if re.search(r'(?<![\w-])z-index\s*:', body):
                has_z_index = True
            if re.search(r'(?<![\w-])(?:padding|margin)(?:-[a-z]+)?\s*:', body):
                has_padding_or_margin = True
                
        if not has_z_index:
            failures.append("MuiDrawer-paper block exists but is missing 'z-index' property")
        if not has_padding_or_margin:
            failures.append("MuiDrawer-paper block exists but is missing 'padding' or 'margin' property")
            
        if has_z_index and has_padding_or_margin:
            log("Passed: MuiDrawer-paper block has z-index and padding/margin properties.")
            
    return len(failures) == 0, failures

def kill_process_tree(process):
    if process is None:
        return
    pid = process.pid
    log(f"Terminating process tree for PID {pid}...")
    if os.name == 'nt':
        try:
            # /F is force, /T is tree
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log("Process tree terminated via taskkill.")
        except Exception as e:
            log(f"Warning: Failed to run taskkill: {e}")
    else:
        try:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
            log("Process terminated via standard terminate/kill.")
        except Exception as e:
            log(f"Warning: Failed to terminate process: {e}")

def test_server():
    log("Starting pre-flight port check...")
    if check_port_occupied(PORT):
        log(f"Error: Port {PORT} is already occupied. Cannot run server check.")
        return False, f"Port {PORT} is occupied"
    
    log(f"Port {PORT} is free. Spawning server...")
    
    cmd = [sys.executable, "-m", "chainlit", "run", "app.py", "--port", str(PORT)]
    log(f"Command: {' '.join(cmd)}")
    
    log_file = open(LOG_FILE_PATH, "w", encoding="utf-8")
    process = None
    server_up = False
    
    try:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, env=env)
        log(f"Server launched with PID {process.pid}. Polling for 20 seconds...")
        
        start_time = time.time()
        while time.time() - start_time < TIMEOUT:
            # Check if process has died early
            if process.poll() is not None:
                log("Error: Server process terminated prematurely.")
                break
                
            try:
                req = urllib.request.Request(SERVER_URL, headers={'User-Agent': 'E2E-Tester'})
                with urllib.request.urlopen(req, timeout=2) as response:
                    if response.getcode() == 200:
                        server_up = True
                        log("Passed: Server responded with HTTP 200 OK!")
                        break
            except urllib.error.URLError:
                # Connection refused, etc.
                pass
            except Exception as e:
                # Socket timeout, etc.
                pass
            time.sleep(0.5)
            
        if not server_up:
            log("Error: Server health check timed out or failed.")
            return False, "Server health check failed"
            
        return True, None
        
    finally:
        if process:
            kill_process_tree(process)
        log_file.close()
        # Clean up log file on success
        if server_up and os.path.exists(LOG_FILE_PATH):
            try:
                os.remove(LOG_FILE_PATH)
            except Exception:
                pass

def main():
    log("=== Running E2E Theme and Layout Verification ===")
    
    css_passed, css_failures = validate_css()
    if css_passed:
        log("CSS Validation: PASSED")
    else:
        log("CSS Validation: FAILED")
        for fail in css_failures:
            log(f"  - {fail}")
            
    server_passed, server_error = test_server()
    if server_passed:
        log("Server Validation: PASSED")
    else:
        log(f"Server Validation: FAILED ({server_error})")
        # Print server logs if they exist and validation failed
        if os.path.exists(LOG_FILE_PATH):
            log("--- Server Log Output (first 30 lines) ---")
            try:
                with open(LOG_FILE_PATH, "r", encoding="utf-8") as lf:
                    lines = lf.readlines()
                    for line in lines[:30]:
                        print(f"  {line.rstrip()}")
            except Exception:
                pass
            log("---------------------------------------")
            try:
                os.remove(LOG_FILE_PATH)
            except Exception:
                pass
                
    log("=== Final Results ===")
    log(f"CSS Status: {'PASSED' if css_passed else 'FAILED'}")
    log(f"Server Status: {'PASSED' if server_passed else 'FAILED'}")
    
    if css_passed and server_passed:
        log("Overall E2E Status: SUCCESS")
        sys.exit(0)
    else:
        log("Overall E2E Status: FAILURE")
        sys.exit(1)

if __name__ == "__main__":
    main()
