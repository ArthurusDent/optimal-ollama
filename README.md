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

## Installation

You need Python installed.

1.  Clone this repository:
    ```bash
    git clone https://github.com/YOUR_USERNAME/optimal-ollama.git
    cd optimal-ollama
    ```

2.  Install dependencies:
    ```bash
    # Linux / Mac
    pip install requests inquirer

    # Windows
    pip install requests inquirer windows-curses
    ```

## Usage

1.  Ensure Ollama is running.
2.  Run the script:
    ```bash
    python optimal_ollama.py
    ```
3.  **Follow the interactive menu:**
    *   Select your Log Source (Docker container name or path to `server.log`).
    *   Select the models you want to benchmark (Space to toggle).
    *   Set your Start/Max Context sizes.
    *   Set your performance limits (GPU %, Speed, VRAM Budget).

4.  **Results:**
    The tool generates two files:
    *   `optimal_ollama_result_TIMESTAMP.csv`: Detailed metrics for analysis.
    *   `optimal_ollama_result_TIMESTAMP_specs.txt`: Snapshot of your hardware config (PCIe speeds, Driver versions, etc.).

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

## License

MIT
