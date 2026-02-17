import requests
import json
import subprocess
import time
import csv
import re
import sys
import platform
import os
from datetime import datetime

# --- IMPORTS & COMPATIBILITY ---
try:
    import inquirer
except ImportError:
    print("\nERROR: 'inquirer' module is missing.")
    print("Please install it via pip:")
    print("  Linux/Mac: pip install inquirer")
    print("  Windows:   pip install inquirer windows-curses\n")
    sys.exit(1)

# --- CONFIGURATION ---

DEFAULT_OLLAMA_URL = "http://localhost:11434"
BASE_FILENAME = "optimal_ollama_result"

# --- VALIDATION FUNCTIONS ---

def validate_float(answers, current):
    try:
        float(current)
        return True
    except ValueError: return False

def validate_int(answers, current):
    try:
        val = int(current)
        if val < 0: return False
        return True
    except ValueError: return False

# --- CLASSES ---

class BenchmarkConfig:
    def __init__(self):
        self.ollama_url = DEFAULT_OLLAMA_URL
        self.selected_models = []
        self.log_mode = "docker"
        self.log_source = "ollama"
        
        # Test Parameters
        self.start_ctx = 4096
        self.max_ctx = 65536
        self.step_size = 4096
        self.num_predict = 100
        
        # Stop Criteria
        self.min_gpu_percent = 0.0
        self.max_sys_ram_gb = 999.0
        self.max_vram_budget_gb = 999.0
        self.min_eval_tps = 0.0
        self.max_duration_seconds = 9999.0

# --- HARDWARE DETECTION ---

def get_system_specs():
    specs = []
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    specs.append(f"Run: {ts}")
    os_name = platform.system()
    specs.append(f"OS: {os_name} {platform.release()} ({platform.machine()})")

    try:
        if os_name == "Windows":
            cpu = subprocess.getoutput("wmic cpu get name").replace("Name", "").strip()
            specs.append(f"CPU: {cpu}")
        elif os_name == "Darwin":
            cpu = subprocess.getoutput("sysctl -n machdep.cpu.brand_string").strip()
            specs.append(f"CPU: {cpu}")
        else:
            cpu = subprocess.getoutput("lscpu | grep 'Model name'").replace('Model name:', '').strip()
            specs.append(f"CPU: {cpu}")
    except: specs.append("CPU: Detection failed")

    try:
        if os_name == "Darwin":
             mem_bytes = subprocess.getoutput("sysctl -n hw.memsize").strip()
             mem_gb = int(mem_bytes) / (1024**3)
             specs.append(f"Total Memory: {mem_gb:.1f} GB")
    except: pass

    specs.append("\n--- GPU Configuration ---")
    if os_name == "Darwin":
        try:
            cores = subprocess.getoutput("system_profiler SPDisplaysDataType | grep 'Total Number of Cores'")
            if cores: specs.append(f"GPU: {cores.strip()}")
            else: specs.append("GPU: Apple Metal (Integrated)")
        except: specs.append("Mac GPU Detect Error")
    else:
        try:
            cmd = ["nvidia-smi", "--query-gpu=index,name,memory.total,power.limit,pcie.link.gen.current,pcie.link.width.current", "--format=csv,noheader"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    specs.append(f"GPU: {line.strip()}")
            else: specs.append("No NVIDIA GPU found")
        except: specs.append("GPU Check skipped")
    return "\n".join(specs)

# --- LOG READER ---

def read_log_lines(config):
    if config.log_mode == "docker":
        try:
            cmd = ["docker", "logs", "--tail", "500", config.log_source]
            res = subprocess.run(cmd, capture_output=True, text=True)
            content = res.stderr + res.stdout
        except: return []
    elif config.log_mode == "file":
        try:
            log_path = os.path.expanduser(config.log_source)
            if os.path.exists(log_path):
                file_size = os.path.getsize(log_path)
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    if file_size > 20000: f.seek(file_size - 20000)
                    content = f.read()
            else: return []
        except: return []
    else: return []
    return content.splitlines()

def get_gpu_stats_from_logs(config):
    try:
        lines = read_log_lines(config)
        for line in reversed(lines):
            match = re.search(r'runner\.size="([\d\.]+)\s+GiB".*?runner\.vram="([\d\.]+)\s+GiB"', line)
            if match:
                size = float(match.group(1))
                vram = float(match.group(2))
                percent = (vram / size) * 100 if size > 0 else 0
                return size, vram, percent
        return 0, 0, 0
    except: return 0, 0, 0

# --- API HELPERS ---

def get_ollama_version(base_url):
    try: return requests.get(f"{base_url}/api/version", timeout=3).json().get("version", "Unknown")
    except: return "Unknown"

def get_model_digest(base_url, model_name):
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=3)
        if resp.status_code == 200:
            for m in resp.json().get("models", []):
                if m["name"] == model_name or m["name"] == f"{model_name}:latest": return m["digest"][:12]
    except: pass
    return "Unknown"

def unload_model(url, model_name):
    try:
        requests.post(f"{url}/api/generate", json={"model": model_name, "keep_alive": 0}, timeout=5)
        time.sleep(1.5)
    except: pass

def preload_model(url, model_name, ctx_size):
    try:
        payload = {"model": model_name, "prompt": "", "stream": False, "options": {"num_ctx": ctx_size, "num_predict": 1, "temperature": 0}}
        requests.post(f"{url}/api/generate", json=payload, timeout=300)
    except: pass

def generate_dummy_prompt(target_tokens):
    code_block = "function test() { const x = 100; return x * 2; } // Filler.\n"
    chars_needed = int(target_tokens * 3.5)
    repeat_count = int(chars_needed / len(code_block)) + 1
    return (code_block * repeat_count)[:chars_needed]

# --- SETUP ---

def setup_benchmark():
    config = BenchmarkConfig()
    BOLD = "\033[1m"
    RESET = "\033[0m"
    
    default_log_mode = "docker"
    default_log_src = "ollama"
    if platform.system() == "Windows":
        default_log_mode = "file"
        default_log_src = os.path.join(os.environ.get('LOCALAPPDATA', ''), "Ollama", "server.log")
    elif platform.system() == "Darwin":
        default_log_mode = "file"
        default_log_src = "~/.ollama/logs/server.log"

    print(f"Connecting to {config.ollama_url} ...")
    try:
        resp = requests.get(f"{config.ollama_url}/api/tags", timeout=3)
        if resp.status_code != 200:
            print("Error: Ollama not responding.")
            sys.exit(1)
        models = [m["name"] for m in resp.json().get("models", [])]
        models.sort()
    except:
        print("Connection Error.")
        sys.exit(1)

    q_logs = [inquirer.List('mode', message="Log Source", choices=['Docker Container', 'Native Installation (Logfile)', 'No Logs'], default='Docker Container' if default_log_mode == 'docker' else 'Native Installation (Logfile)')]
    ans_logs = inquirer.prompt(q_logs)
    if ans_logs['mode'] == 'Docker Container':
        config.log_mode = "docker"
        config.log_source = inquirer.prompt([inquirer.Text('src', message="Container Name", default="ollama")])['src']
    elif ans_logs['mode'] == 'Native Installation (Logfile)':
        config.log_mode = "file"
        config.log_source = inquirer.prompt([inquirer.Text('src', message="Log Path", default=default_log_src)])['src']
    else: config.log_mode = "none"

    q_models = [inquirer.Checkbox('models', message=f"Select Models ({BOLD}Space{RESET}=Select, {BOLD}Enter{RESET}=Confirm)", choices=models)]
    while True:
        ans_models = inquirer.prompt(q_models)
        if ans_models is None: sys.exit(0)
        if not ans_models['models']:
            print(f"\n{BOLD}>> Error: Select at least one model!{RESET}\n")
            continue
        config.selected_models = ans_models['models']
        break

    q_params = [
        inquirer.Text('start_ctx', message="Start Context", default="4096", validate=validate_int),
        inquirer.Text('max_ctx',   message="Max Context", default="65536", validate=validate_int),
        inquirer.Text('step_size', message="Step Size", default="4096", validate=validate_int),
        inquirer.Text('num_gen',   message="Tokens to Generate", default="100", validate=validate_int),
    ]
    print("\n--- Test Parameters ---")
    ans_params = inquirer.prompt(q_params)
    config.start_ctx = int(ans_params['start_ctx'])
    config.max_ctx = int(ans_params['max_ctx'])
    config.step_size = int(ans_params['step_size'])
    config.num_predict = int(ans_params['num_gen'])

    if config.step_size <= 0:
        print("Error: Step Size must be > 0")
        sys.exit(1)

    q_limits = [
        inquirer.Text('min_gpu', message="Min GPU %", default="0" if platform.system() == "Darwin" else "90", validate=validate_float),
        inquirer.Text('max_ram', message="Max Sys-RAM GB", default="32.0", validate=validate_float),
        inquirer.Text('max_vram', message="Max VRAM Budget GB", default="24.0", validate=validate_float),
        inquirer.Text('min_tps', message="Min Eval Speed t/s", default="2.0", validate=validate_float),
        inquirer.Text('max_time', message="Max Time (s)", default="120.0", validate=validate_float),
    ]
    print("\n--- Stop Criteria ---")
    ans_limits = inquirer.prompt(q_limits)
    config.min_gpu_percent = float(ans_limits['min_gpu'])
    config.max_sys_ram_gb = float(ans_limits['max_ram'])
    config.max_vram_budget_gb = float(ans_limits['max_vram'])
    config.min_eval_tps = float(ans_limits['min_tps'])
    config.max_duration_seconds = float(ans_limits['max_time'])
    
    return config

# --- MAIN ---

def run_benchmark():
    config = setup_benchmark()
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = f"{BASE_FILENAME}_{ts_str}.csv"
    
    with open(f"{BASE_FILENAME}_{ts_str}_specs.txt", "w") as f: f.write(get_system_specs())
    ollama_ver = get_ollama_version(config.ollama_url)

    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Timestamp", "Ollama_Ver", "Model", "Model_Hash", 
            "Target_Ctx", "Actual_Ctx", "Actual_Gen_Tokens",
            "Eval_Speed (t/s)", "Prompt_Speed (t/s)", "Total_Duration (s)", 
            "GPU_Percent", "Sys_RAM_Used_GiB", "VRAM_Used_GiB", 
            "Status", "Stop_Reason",
            "AA_Intelligence", "AA_Coding", "AA_Agentic"
        ])

    print("\n" + "="*70)
    print(f"Starting Benchmark V16")
    print(f"Gen Tokens: {config.num_predict}")
    print("="*70 + "\n")

    for model in config.selected_models:
        model_hash = get_model_digest(config.ollama_url, model)
        print(f"--- Testing Model: {model} ({model_hash}) ---")
        
        current_ctx = config.start_ctx
        
        while current_ctx <= config.max_ctx:
            # 1. Unload & Warmup
            unload_model(config.ollama_url, model)
            print(f"  > Ctx {current_ctx:<6} ... (Loading)", end="", flush=True)
            preload_model(config.ollama_url, model, current_ctx)
            
            # 2. Test
            print("\r" + f"  > Ctx {current_ctx:<6} ... (Testing)", end="", flush=True)
            prompt = generate_dummy_prompt(int(current_ctx * 1.1))
            
            payload = {
                "model": model, "prompt": prompt, "stream": False, 
                "options": {
                    "num_ctx": current_ctx, 
                    "num_predict": config.num_predict, 
                    "temperature": 0.1
                }
            }

            # Initialize safe defaults BEFORE try block to prevent NameError
            ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            actual_gen = 0
            actual_ctx = 0
            eval_tps = 0
            prompt_tps = 0
            total_dur = 0
            gpu_percent = 0
            sys_ram_used = 0
            vram_gib = 0
            should_stop = False
            stop_reason = ""
            status = "FAIL" # Default

            try:
                hard_limit = 1800
                net_timeout = max(hard_limit, config.max_duration_seconds + 60)
                
                # EXECUTE REQUEST
                resp = requests.post(f"{config.ollama_url}/api/generate", json=payload, timeout=net_timeout)
                
                # Update timestamp to when response arrived (optional, but consistent)
                ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if resp.status_code == 200:
                    data = resp.json()
                    
                    total_dur = data.get("total_duration", 0) / 1e9
                    eval_tps = data.get("eval_count", 0) / (data.get("eval_duration", 0) / 1e9 or 1)
                    prompt_tps = data.get("prompt_eval_count", 0) / (data.get("prompt_eval_duration", 0) / 1e9 or 1)
                    actual_ctx = data.get("prompt_eval_count", 0)
                    actual_gen = data.get("eval_count", 0)
                    
                    size_gib, vram_gib, gpu_percent = get_gpu_stats_from_logs(config)
                    sys_ram_used = max(0, size_gib - vram_gib)
                    
                    ignore_gpu = (config.log_mode == "none") or (gpu_percent == 0 and platform.system() == "Darwin")
                    status = "OK"

                    # Limits
                    if actual_ctx < (current_ctx * 0.99):
                        status = f"TRUNCATED ({actual_ctx})"
                        stop_reason = "Context Limit"
                        should_stop = True
                    elif not ignore_gpu and gpu_percent < config.min_gpu_percent - 0.1:
                        status = "FAIL_GPU_%"
                        stop_reason = f"GPU {gpu_percent:.1f}% < {config.min_gpu_percent}%"
                        should_stop = True
                    elif vram_gib > config.max_vram_budget_gb:
                        status = "FAIL_VRAM"
                        stop_reason = f"VRAM {vram_gib:.1f}GiB > {config.max_vram_budget_gb}GiB"
                        should_stop = True
                    elif sys_ram_used > config.max_sys_ram_gb:
                        status = "FAIL_RAM"
                        stop_reason = f"RAM {sys_ram_used:.1f}GiB > {config.max_sys_ram_gb}GiB"
                        should_stop = True
                    elif eval_tps < config.min_eval_tps:
                        status = "FAIL_SPEED"
                        stop_reason = f"Speed {eval_tps:.1f} < {config.min_eval_tps} t/s"
                        should_stop = True
                    elif total_dur > config.max_duration_seconds:
                        status = "FAIL_TIME"
                        stop_reason = f"Time {total_dur:.1f}s > {config.max_duration_seconds}s"
                        should_stop = True

                    print(f"\r  > Ctx {current_ctx:<6} -> TPS: {eval_tps:>5.1f} | Gen: {actual_gen} | Time: {total_dur:>4.1f}s | Mem: {vram_gib:>4.1f}GiB | {status}      ")
                    
                    with open(csv_file, 'a', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            ts_now, ollama_ver, model, model_hash, 
                            current_ctx, actual_ctx, actual_gen,
                            f"{eval_tps:.2f}", f"{prompt_tps:.2f}", f"{total_dur:.2f}", 
                            f"{gpu_percent:.1f}", f"{sys_ram_used:.2f}", f"{vram_gib:.2f}", 
                            status, stop_reason, "", "", ""
                        ])
                    
                    if should_stop:
                        print(f"    -> STOP: {stop_reason}")
                        print(f"    -> Optimal Context ca.: {current_ctx - config.step_size}")
                        break
                    
                    # Loop continue (Success)
                    current_ctx += config.step_size

                else:
                    # HTTP Error (500 etc)
                    size_gib, vram_gib, gpu_percent = get_gpu_stats_from_logs(config)
                    sys_ram_used = max(0, size_gib - vram_gib)
                    print(f"\r  > Ctx {current_ctx:<6} -> HTTP {resp.status_code} | Mem: {vram_gib:>4.1f}GiB | FAIL_CRASH      ")
                    
                    with open(csv_file, 'a', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            ts_now, ollama_ver, model, model_hash, current_ctx, 0, 0, 
                            0, 0, 0, f"{gpu_percent:.1f}", f"{sys_ram_used:.2f}", f"{vram_gib:.2f}", 
                            f"FAIL_{resp.status_code}", "Server Error", "", "", ""
                        ])
                    
                    print(f"    -> STOP: Server Error {resp.status_code}")
                    print(f"    -> Optimal Context ca.: {current_ctx - config.step_size}")
                    break # Break loop on error

            except Exception as e:
                print(f"\nCrash: {e}")
                break
            
            time.sleep(1)

if __name__ == "__main__":
    run_benchmark()
