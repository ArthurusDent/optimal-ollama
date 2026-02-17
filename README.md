# Optimal Ollama 🦙

**Optimal Ollama** is a cross-platform benchmarking and tuning tool designed to find the "Sweet Spot" for your local LLMs. It helps you determine the maximum context window a model can handle on your specific hardware before performance degrades or memory limits are exceeded.

## Why use this?

Running local LLMs involves a trade-off between **Context Size**, **Speed (Tokens/s)**, and **VRAM usage**.
*   If you set the context too high, the model might offload layers to the slow system RAM (CPU), killing performance.
*   If you set it too low, you are wasting the potential of your hardware.

**Optimal Ollama** automates the process of finding the perfect balance.

## Features

*   **Auto-Discovery:** Automatically finds all models installed in Ollama.
*   **Auto-Tuning:** Incrementally increases context size until a limit is hit.
*   **Hardware-Aware:**
    *   **NVIDIA (Linux/Windows):** Monitors VRAM, GPU Load, and Power Limits.
    *   **Apple Silicon (Mac):** Monitors Unified Memory usage.
*   **Precision Benchmarking:**
    *   **Warmup Phase:** Preloads models into VRAM before measuring to ensure accurate timing (excludes disk loading time).
    *   **Read vs. Write:** Measures "Prompt Processing" (Reading files) and "Token Generation" (Writing code) separately.
    *   **Workload Simulation:** Configurable number of tokens to generate (e.g., test how the model behaves when writing 500 lines of code vs. just a short answer).
*   **Smart Log Parsing:** Reads Ollama logs (Docker or Native) to calculate exact VRAM usage / Split ratios.
*   **Stop Criteria:** Define your own limits:
    *   Min. Generation Speed (e.g., "Stop if < 5 t/s")
    *   Max. VRAM Budget (e.g., "Leave 4GB free for other apps")
    *   Max. System RAM Spillover
    *   Max. Response Time (Latency)

## Installation & Setup (Recommended)

**IMPORTANT:** This script has been vibe-coded and has only been tested under Linux. Therefore it might not fully work on Windows or Mac. Please report any issues.

To avoid conflicts with your system's Python installation, we strongly recommend using a **virtual environment**.

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/optimal-ollama.git
cd optimal-ollama
```

### 2. Create a Virtual Environment
Run the following command to create an isolated environment in the folder `.venv`.

**Linux / macOS:**
```bash
# On Ubuntu/Debian, you might need: sudo apt install python3-venv
python3 -m venv .venv
```

**Windows:**
```cmd
python -m venv .venv
```

### 3. Activate the Environment
You must activate the environment **every time** you open a new terminal window to run the script.

**Linux / macOS:**
```bash
source .venv/bin/activate
```
*(Your prompt should now show `(.venv)`)*

**Windows (Command Prompt):**
```cmd
.venv\Scripts\activate
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```
*(If you get a permission error on PowerShell, run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`)*

### 4. Install Dependencies
Now install the required libraries into the virtual environment.

**Linux / macOS:**
```bash
pip install requests inquirer
```

**Windows:**
```bash
pip install requests inquirer windows-curses
```

## Usage

1.  Ensure Ollama is running.
2.  Make sure your virtual environment is active (see Step 3 above).
3.  Run the script:
    ```bash
    python optimal_ollama.py
    ```
4.  **Follow the interactive menu:**
    *   Select your Log Source (Docker container name or path to `server.log`).
    *   Select the models you want to benchmark (Space to toggle).
    *   **Test Parameters:**
        *   Start / Max Context Size
        *   Step Size
        *   **Tokens to Generate:** Set this higher (e.g., 200-500) to simulate heavy writing tasks, or lower (20) for quick speed checks.
    *   **Stop Criteria:** Set your performance limits (GPU %, Speed, VRAM Budget, Time Limit).

5.  **Results:**
    The tool generates two files:
    *   `optimal_ollama_result_TIMESTAMP_specs.txt`: Snapshot of your hardware config.
    *   `optimal_ollama_result_TIMESTAMP.csv`: Detailed metrics containing:
        *   `Target_Ctx` vs `Actual_Ctx`: Did the model respect the context size?
        *   `Actual_Gen_Tokens`: How many tokens were actually written.
        *   `Eval_Speed (t/s)`: **Writing speed** (crucial for agents writing code).
        *   `Prompt_Speed (t/s)`: **Reading speed** (crucial for agents analyzing files).
        *   `GPU_Percent` / `Sys_RAM`: How much of the model was offloaded to the slow CPU RAM.
        *   `Stop_Reason`: Why the test ended (e.g., "Speed < 5 t/s").

## Platform Notes

### Linux (Docker)
Works out of the box. Select "Docker Container" in the menu and provide the container name (default: `ollama`).

### Windows
Select "Native Installation". The script automatically suggests the default log path: `%LOCALAPPDATA%\Ollama\server.log`.

### Mac (Apple Silicon)
*   Select "Native Installation".
*   Default log path: `~/.ollama/logs/server.log`.
*   **Note:** If Ollama runs as a background service, logs might not update in real-time. For best results, stop the service and run `ollama serve` in a terminal window before benchmarking.
*   Set "Min GPU %" to 0 (since Unified Memory behaves differently). Use "VRAM Budget" instead.

## Adding data from intelligence benchmarks

Comparing models without official benchmark ratings would disregard important data about model performance.
You can manually add data from sites like [Artificial Analysis](https://artificialanalysis.ai/) to the last columns in the CSV file.
If you don't want to analyze the completed CSV yourself, feed it to an LLM.

## License

MIT
