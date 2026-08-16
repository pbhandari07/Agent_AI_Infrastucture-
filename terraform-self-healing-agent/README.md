# Terraform Self-Healing Agent - Ollama & Qwen2.5 Tool-Using Agent

This project implements an autonomous, local tool-using agent using Python, Ollama, and `qwen2.5-coder:1.5b`.

## Prerequisites

- Windows OS
- Python 3.14+
- Ollama running locally (`http://localhost:11434`)
- Model `qwen2.5-coder:1.5b` pulled (`ollama pull qwen2.5-coder:1.5b`)
- Virtual environment in `.venv` with `ollama` package installed

## Setup & Running Connection Test

1. Activate virtual environment:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

2. Run connection test:
   ```powershell
   python test_ollama.py
   ```

---

## Agent Architecture & Tool Execution Loop

### What is an Agent Loop?
An **agent loop** is a multi-turn reasoning and execution cycle. Instead of providing a single static answer, the LLM receives a user goal, evaluates what actions are necessary, selects and calls structured tools, receives empirical execution results, and iterates until the goal is achieved.

```
          +-----------------------+
          |       User Goal       |
          +-----------+-----------+
                      |
                      v
          +-----------------------+
          |      Ollama / Qwen    |
          +-----------+-----------+
                      |
        Does model request a tool?
         /                     \
       YES                      NO
        |                        |
        v                        v
+---------------+        +---------------+
| Execute Tool  |        |  Final Answer |
+-------+-------+        +---------------+
        |
        v
+---------------+
| Send Result   |
| Back to Model |
+-------+-------+
        |
        +-----> Repeat (Max 8 Iterations)
```

### Available Sandboxed Tools

All tools are strictly constrained to the project root directory. Path traversal (`..`) or accessing files outside the workspace is denied.

1. **`list_files(path: str = ".")`**
   - Lists files and subdirectories inside project-relative paths.
   - Denies access outside the project root.

2. **`read_file(path: str)`**
   - Reads text file contents within project root.
   - Rejects non-existent or out-of-sandbox paths.

3. **`write_file(path: str, content: str)`**
   - Writes or updates text files inside project root.
   - Creates parent directories automatically. Never deletes files.

4. **`run_python_test(path: str)`**
   - Executes Python test files using the project `.venv` interpreter (`sys.executable`).
   - Captures stdout, stderr, and exit codes safely without `shell=True`.

### How Qwen Chooses a Tool
When presented with conversation history and available tools, Qwen outputs structured tool invocation requests (either via native Ollama tool call schemas or JSON tool call blocks). The agent loop intercepts these requests, extracts tool parameters, and dispatches them to python functions in `tools.py`.

### How Tool Results are Returned to Qwen
Once a tool executes, its string output (file content, directory listing, or unit test output/stderr) is formatted into a message with role `"tool"` and appended to the conversation context. Qwen reads this feedback to determine its next action.

---

## How to Run the Bug Fix Demo

1. Run the initial test independently to confirm failure:
   ```powershell
   python demo/test_buggy_calculator.py
   ```
   *(Expected output: `AssertionError: -1 != 5`)*

2. Run the tool-using agent:
   ```powershell
   python agent.py
   ```
   *(The agent will inspect files, identify the subtraction bug in `demo/buggy_calculator.py`, rewrite `add()`, run the test, and output the final answer).*

3. Run the test independently again to verify the fix:
   ```powershell
   python demo/test_buggy_calculator.py
   ```
   *(Expected output: `Ran 4 tests ... OK`)*
