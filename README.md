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
*   **Smart Log Parsing:** Reads Ollama logs (Docker or Native) to calculate exact VRAM usage.
*   **Stop Criteria:** Define your own limits:
    *   Min. Generation Speed (e.g., "Stop if < 5 t/s")
    *   Max. VRAM Budget (e.g., "Leave 4GB free for other apps")
    *   Max. System RAM Spillover
    *   Max. Response Time

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
    *   Set your Start/Max Context sizes.
    *   Set your performance limits (GPU %, Speed, VRAM Budget).

5.  **Results:**
    The tool generates two files:
    *   `optimal_ollama_result_TIMESTAMP.csv`: Detailed metrics for analysis.
    *   `optimal_ollama_result_TIMESTAMP_specs.txt`: Snapshot of your hardware config.

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
Open the CSV file with the results in your favorite spreadsheet software. The last three columns can be used to add data from [Artificial Analysis](https://artificialanalysis.ai/) (or any other benchmark you'd like to compare your models to).

## License

MIT
