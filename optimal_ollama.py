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

# ANSI Colors for bold text
BOLD = "\033[1m"
RESET = "\033[0m"

# --- VALIDATION FUNCTIONS ---

def validate_float(answers, current):
    try:
        float(current)
        return True
    except ValueError:
        return False

def validate_int(answers, current):
    try:
        int(current)
        return True
    except ValueError:
        return False

# --- CLASSES ---

class BenchmarkConfig:
    def __init__(self):
        self.ollama_url = DEFAULT_OLLAMA_URL
        self.selected_models = []
        self.log_mode = "docker" # 'docker', 'file', or 'none'
        self.log_source = "ollama" # Container name or file path
        
        # Test Parameters
        self.start_ctx = 4096
        self.max_ctx = 65536
        self.step_size = 4096
        
        # Stop Criteria
        self.min_gpu_percent = 0.0
        self.max_sys_ram_gb = 999.0
        self.max_vram_budget_gb = 999.0
        self.min_eval_tps = 0.0
        self.max_duration_seconds = 9999.0

# --- HARDWARE DETECTION (CROSS PLATFORM) ---

def get_system_specs():
    specs = []
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    specs.append(f"Run: {ts}")
    
    os_name = platform.system()
    specs.append(f"OS: {os_name} {platform.release()} ({platform.machine()})")

    # 1. CPU DETECTION
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
    except:
        specs.append("CPU: Detection failed")

    # 2. RAM DETECTION (Rough Estimate)
    try:
        if os_name == "Darwin":
             mem_bytes = subprocess.getoutput("sysctl -n hw.memsize").strip()
             mem_gb = int(mem_bytes) / (1024**3)
             specs.append(f"Total Memory: {mem_gb:.1f} GB")
    except: pass

    # 3. GPU DETECTION
    specs.append("\n--- GPU Configuration ---")
    
    if os_name == "Darwin":
        try:
            cores = subprocess.getoutput("system_profiler SPDisplaysDataType | grep 'Total Number of Cores'")
            if cores:
                specs.append(f"GPU: {cores.strip()}")
            else:
                specs.append("GPU: Apple Metal (Integrated)")
            specs.append("Note: On Mac, VRAM = Unified Memory.")
        except: specs.append("Mac GPU Detect Error")
        
    else: # Windows & Linux (Targeting NVIDIA)
        try:
            cmd = [
                "nvidia-smi", 
                "--query-gpu=index,name,memory.total,power.limit,pcie.link.gen.current,pcie.link.width.current", 
                "--format=csv,noheader"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    p = [x.strip() for x in line.split(',')]
                    if len(p) >= 6:
                        specs.append(f"GPU {p[0]}: {p[1]} ({p[2]})")
                        specs.append(f"  -> Power Limit: {p[3]}")
                        specs.append(f"  -> PCIe Link:   Gen{p[4]} x{p[5]}")
            else:
                specs.append("No NVIDIA GPU found (nvidia-smi returned error)")
        except FileNotFoundError:
             specs.append("nvidia-smi not found in PATH")
        except Exception as e:
            specs.append(f"GPU Error: {e}")

    return "\n".join(specs)

# --- LOG READER (UNIVERSAL) ---

def read_log_lines(config):
    """Reads the last lines from Docker OR a log file."""
    content = ""
    
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
                # Read only the last 20 KB to save performance
                file_size = os.path.getsize(log_path)
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    if file_size > 20000:
                        f.seek(file_size - 20000)
                    content = f.read()
            else:
                return []
        except: return []

    return content.splitlines()

def get_gpu_stats_from_logs(config):
    try:
        lines = read_log_lines(config)
        for line in reversed(lines):
            # Regex for llama.cpp memory output
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
    try:
        resp = requests.get(f"{base_url}/api/version", timeout=3)
        if resp.status_code == 200:
            return resp.json().get("version", "Unknown")
    except: pass
    return "Unknown"

def get_model_digest(base_url, model_name):
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            for m in models:
                if m["name"] == model_name or m["name"] == f"{model_name}:latest":
                    return m["digest"][:12]
    except: pass
    return "Unknown"

def unload_model(url, model_name):
    try:
        requests.post(f"{url}/api/generate", json={"model": model_name, "keep_alive": 0}, timeout=5)
        time.sleep(1.5)
    except: pass

def preload_model(url, model_name, ctx_size):
    """
    Lädt das Modell mit der Ziel-Kontextgröße in den Speicher (Warmup).
    Sendet einen leeren Prompt, damit Ollama den VRAM reserviert.
    """
    try:
        # Minimaler Request: 1 Token generieren
        payload = {
            "model": model_name, 
            "prompt": " ", 
            "stream": False, 
            "options": {
                "num_ctx": ctx_size, 
                "num_predict": 1, 
                "temperature": 0
            }
        }
        # Timeout großzügig wählen, da Laden bei großen Modellen dauern kann
        # Wir ignorieren das Ergebnis, wir wollen nur, dass es geladen ist.
        requests.post(f"{url}/api/generate", json=payload, timeout=300)
    except:
        pass

def generate_dummy_prompt(target_tokens):
    code_block = "function test() { const x = 100; return x * 2; } // Filler.\n"
    chars_needed = int(target_tokens * 3.5)
    repeat_count = int(chars_needed / len(code_block)) + 1
    return (code_block * repeat_count)[:chars_needed]

# --- SETUP & MENU ---

def setup_benchmark():
    config = BenchmarkConfig()
    
    # 0. OS Default Log Paths
    default_log_mode = "docker"
    default_log_src = "ollama"
    
    if platform.system() == "Windows":
        default_log_mode = "file"
        local_app_data = os.environ.get('LOCALAPPDATA', '')
        default_log_src = os.path.join(local_app_data, "Ollama", "server.log")
        
    elif platform.system() == "Darwin":
        default_log_mode = "file"
        default_log_src = os.path.expanduser("~/.ollama/logs/server.log")

    print(f"Connecting to {config.ollama_url} ...")
    try:
        resp = requests.get(f"{config.ollama_url}/api/tags", timeout=3)
        if resp.status_code != 200:
            print("Error: Ollama is not responding. Is the server running?")
            sys.exit(1)
        models = [m["name"] for m in resp.json().get("models", [])]
        models.sort()
    except Exception as e:
        print(f"Connection Error: {e}")
        sys.exit(1)

    if not models:
        print("No models found in Ollama!")
        sys.exit(1)

    # Q1: Log Configuration
    q_logs = [
        inquirer.List('mode',
            message="How is Ollama running? (For GPU/VRAM log analysis)",
            choices=['Docker Container', 'Native Installation (Logfile)', 'No Logs (Skip VRAM check)'],
            default='Docker Container' if default_log_mode == 'docker' else 'Native Installation (Logfile)'
        ),
    ]
    ans_logs = inquirer.prompt(q_logs)
    
    if ans_logs['mode'] == 'Docker Container':
        config.log_mode = "docker"
        ans_src = inquirer.prompt([inquirer.Text('src', message="Docker Container Name", default="ollama")])
        config.log_source = ans_src['src']
        
    elif ans_logs['mode'] == 'Native Installation (Logfile)':
        config.log_mode = "file"
        ans_src = inquirer.prompt([inquirer.Text('src', message="Path to server.log", default=default_log_src)])
        config.log_source = ans_src['src']
    else:
        config.log_mode = "none"

    # Q2: Models (In einer Schleife, bis eine Auswahl getroffen wurde)
    q_models = [
        inquirer.Checkbox('models', 
            message=f"Select Models ({BOLD}Space{RESET} to select, {BOLD}Enter{RESET} to confirm)", 
            choices=models,
            # validate=... entfernen wir hier, da es unzuverlässig ist
        )
    ]
    
    while True:
        ans_models = inquirer.prompt(q_models)
        
        # Fall 1: Benutzer drückt Strg+C (Abbruch) -> ans_models ist None
        if ans_models is None:
            sys.exit(0)
            
        # Fall 2: Liste ist leer -> Fehler anzeigen und Schleife wiederholen
        if not ans_models['models']:
            print(f"\n{BOLD}>> Error: You must select at least one model using SPACE!{RESET}\n")
            continue
            
        # Fall 3: Auswahl getroffen -> Schleife verlassen
        config.selected_models = ans_models['models']
        break

    # Q3: Parameters (With Integer Validation)
    q_params = [
        inquirer.Text('start_ctx', message="Start Context Size", default="4096", validate=validate_int),
        inquirer.Text('max_ctx',   message="Max Context Size", default="65536", validate=validate_int),
        inquirer.Text('step_size', message="Step Size", default="4096", validate=validate_int),
    ]
    print("\n--- Test Parameters ---")
    ans_params = inquirer.prompt(q_params)
    config.start_ctx = int(ans_params['start_ctx'])
    config.max_ctx = int(ans_params['max_ctx'])
    config.step_size = int(ans_params['step_size'])

    # Q4: Limits (With Float Validation)
    q_limits = [
        inquirer.Text('min_gpu', message="a) Min GPU % (0 for Mac/CPU)", default="0" if platform.system() == "Darwin" else "90", validate=validate_float),
        inquirer.Text('max_ram', message="b) Max System RAM GB (Stop if exceeded)", default="32.0", validate=validate_float),
        inquirer.Text('max_vram', message="c) VRAM/Unified Budget GB (Stop if exceeded)", default="24.0", validate=validate_float),
        inquirer.Text('min_tps', message="d) Min Speed t/s (Stop if slower)", default="5.0", validate=validate_float),
        inquirer.Text('max_time', message="e) Max Time per Request (s)", default="60.0", validate=validate_float),
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
    # 1. Setup & Konfiguration abfragen
    config = setup_benchmark()
    
    # 2. Dateinamen vorbereiten
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"{BASE_FILENAME}_{timestamp_str}.csv"
    
    # 3. System-Specs speichern
    specs_text = get_system_specs()
    with open(f"{BASE_FILENAME}_{timestamp_str}_specs.txt", "w") as f:
        f.write(specs_text)
    
    # Kurzer System-Check auf der Konsole
    print("\n--- System Check ---")
    for line in specs_text.splitlines():
        if any(x in line for x in ["OS:", "CPU:", "GPU", "Memory", "Power"]):
            print(line)
    print(f"Log Source: {config.log_mode} -> {config.log_source}")
    print("--------------------\n")

    ollama_ver = get_ollama_version(config.ollama_url)

    # 4. CSV Header schreiben
    with open(csv_filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Timestamp", "Ollama_Ver", "Model", "Model_Hash", 
            "Target_Ctx", "Actual_Ctx", 
            "Eval_Speed (t/s)", "Prompt_Speed (t/s)", "Total_Duration (s)", 
            "GPU_Percent", "Sys_RAM_Used_GB", "VRAM_Used_GB", 
            "Status", "Stop_Reason",
            "AA_Intelligence", "AA_Coding", "AA_Agentic"
        ])

    print("\n" + "="*70)
    print(f"Starting Benchmark")
    print(f"Range: {config.start_ctx} -> {config.max_ctx} (Step: {config.step_size})")
    print(f"Limits: VRAM <{config.max_vram_budget_gb}GB | Speed >{config.min_eval_tps} t/s | Time <{config.max_duration_seconds}s")
    print("="*70 + "\n")

    # 5. Iteration über Modelle
    for model in config.selected_models:
        model_hash = get_model_digest(config.ollama_url, model)
        print(f"--- Testing Model: {model} ({model_hash}) ---")
        
        current_ctx = config.start_ctx
        
        while current_ctx <= config.max_ctx:
            # A) Aufräumen (Clean Slate)
            unload_model(config.ollama_url, model)
            
            # B) Warmup / Preload (Zeit wird NICHT gemessen)
            # \r springt an den Zeilenanfang zurück, end="" verhindert neue Zeile
            print(f"  > Ctx {current_ctx:<6} ... (Loading)", end="", flush=True)
            
            preload_model(config.ollama_url, model, current_ctx)
            
            # C) Der eigentliche Benchmark (Modell ist jetzt im VRAM)
            # Wir überschreiben "(Loading)" mit "(Testing)"
            print("\r" + f"  > Ctx {current_ctx:<6} ... (Testing)", end="", flush=True)
            
            prompt = generate_dummy_prompt(int(current_ctx * 1.1))
            
            payload = {
                "model": model, 
                "prompt": prompt, 
                "stream": False, 
                "options": {
                    "num_ctx": current_ctx, 
                    "num_predict": 20, 
                    "temperature": 0.1
                }
            }

            try:
                # Timeout: User-Limit + 15s Puffer
                safe_timeout = max(60, config.max_duration_seconds + 15)
                
                # HIER startet die Messung
                resp = requests.post(f"{config.ollama_url}/api/generate", json=payload, timeout=safe_timeout)
                ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if resp.status_code == 200:
                    data = resp.json()
                    
                    # Metriken berechnen
                    # load_duration sollte jetzt vernachlässigbar sein
                    total_dur = data.get("total_duration", 0) / 1e9
                    eval_tps = data.get("eval_count", 0) / (data.get("eval_duration", 0) / 1e9 or 1)
                    prompt_tps = data.get("prompt_eval_count", 0) / (data.get("prompt_eval_duration", 0) / 1e9 or 1)
                    actual_ctx = data.get("prompt_eval_count", 0)
                    
                    # Hardware-Stats holen (jetzt wo das Modell heiß ist)
                    size_gib, vram_gib, gpu_percent = get_gpu_stats_from_logs(config)
                    sys_ram_used = max(0, size_gib - vram_gib)
                    
                    # Mac Special Case: Ignore GPU% check if no logs/native
                    ignore_gpu_check = (config.log_mode == "none") or (gpu_percent == 0 and platform.system() == "Darwin")

                    # Abbruch-Kriterien prüfen
                    stop_reason = ""
                    status = "OK"
                    should_stop = False

                    # 1. Truncation (1% Toleranz)
                    if actual_ctx < (current_ctx * 0.99):
                        status = f"TRUNCATED ({actual_ctx})"
                        stop_reason = "Context Limit Reached"
                        should_stop = True

                    # 2. Hardware Limits
                    elif not ignore_gpu_check and gpu_percent < config.min_gpu_percent - 0.1:
                        status = "FAIL_GPU_%"
                        stop_reason = f"GPU {gpu_percent:.1f}% < {config.min_gpu_percent}%"
                        should_stop = True
                    
                    elif vram_gib > config.max_vram_budget_gb:
                        status = "FAIL_VRAM_BUDGET"
                        stop_reason = f"VRAM {vram_gib:.1f}GB > Budget {config.max_vram_budget_gb}GB"
                        should_stop = True

                    elif sys_ram_used > config.max_sys_ram_gb:
                        status = "FAIL_RAM"
                        stop_reason = f"RAM {sys_ram_used:.1f}GB > Limit {config.max_sys_ram_gb}GB"
                        should_stop = True
                    
                    # 3. Performance Limits
                    elif eval_tps < config.min_eval_tps:
                        status = "FAIL_SPEED"
                        stop_reason = f"Speed {eval_tps:.1f} < {config.min_eval_tps} t/s"
                        should_stop = True
                    elif total_dur > config.max_duration_seconds:
                        status = "FAIL_TIME"
                        stop_reason = f"Time {total_dur:.1f}s > {config.max_duration_seconds}s"
                        should_stop = True

                    # Zeile überschreiben mit Ergebnis
                    # Wir nutzen Leerzeichen am Ende, um Reste von "(Testing)" zu löschen
                    print(f"\r  > Ctx {current_ctx:<6} -> TPS: {eval_tps:>5.1f} | Time: {total_dur:>4.1f}s | VRAM: {vram_gib:>4.1f}GB | {status}      ")
                    
                    # CSV Speichern
                    with open(csv_filename, 'a', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            ts_now, ollama_ver, model, model_hash, 
                            current_ctx, actual_ctx, 
                            f"{eval_tps:.2f}", f"{prompt_tps:.2f}", f"{total_dur:.2f}", 
                            f"{gpu_percent:.1f}", f"{sys_ram_used:.2f}", f"{vram_gib:.2f}", 
                            status, stop_reason, "", "", ""
                        ])
                    
                    # Abbruch verarbeiten
                    if should_stop:
                        print(f"    -> STOP: {stop_reason}")
                        suggestion = current_ctx - config.step_size
                        if suggestion < config.start_ctx:
                             print(f"    -> Model unsuitable for criteria.")
                        else:
                             print(f"    -> Optimal Context ca.: {suggestion}")
                        break

                    current_ctx += config.step_size

                else:
                    print(f"\nHTTP Error {resp.status_code}")
                    break

            except Exception as e:
                print(f"\nCrash/Timeout: {e}")
                break
            
            # Kurze Pause für System-Erholung
            time.sleep(1)

if __name__ == "__main__":
    run_benchmark()
