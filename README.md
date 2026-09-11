# Terraform Self-Healing Agent

### Local Tool-Using AI Agent with Ollama & Qwen2.5-Coder

An autonomous, local **tool-using AI agent** built with **Python,
Ollama, and Qwen2.5-Coder (`qwen2.5-coder:1.5b`)**.

The project demonstrates an agentic workflow where an LLM does more than
generate a static response: it can inspect a workspace, select
structured tools, execute actions, observe the results, and iterate
until the requested task is completed.

> **Current demo:** The repository demonstrates the
> self-healing/tool-execution pattern through an automated Python
> bug-fix workflow. The same architecture can be extended to
> infrastructure workflows such as Terraform validation, diagnosis, and
> remediation.

------------------------------------------------------------------------

## 🚀 What This Project Demonstrates

-   Local LLM inference using **Ollama**
-   **Qwen2.5-Coder 1.5B** as the reasoning/model component
-   Tool-using / agentic execution loop
-   Structured tool invocation
-   Workspace sandboxing and path validation
-   Automated file inspection and modification
-   Test execution and result feedback
-   Iterative reasoning with a maximum of **8 agent iterations**
-   A foundation for extending AI agents toward **DevOps and
    infrastructure self-healing**

------------------------------------------------------------------------

## 🏗️ Agent Architecture

The agent follows a closed-loop **observe → reason → act → verify**
workflow.

``` text
                    ┌───────────────────┐
                    │     User Goal     │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │   Ollama / Qwen   │
                    │  Qwen2.5-Coder    │
                    └─────────┬─────────┘
                              │
                    Tool request?
                       /          \
                     YES           NO
                      │             │
                      ▼             ▼
              ┌──────────────┐  ┌──────────────┐
              │ Execute Tool │  │ Final Answer │
              └──────┬───────┘  └──────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ Tool Result  │
              │ stdout/stderr│
              │ file content │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │ Send Result  │
              │ Back to Qwen │
              └──────┬───────┘
                     │
                     └──────► Repeat
                              (max 8 iterations)
```

### What is an Agent Loop?

An **agent loop** is a multi-step reasoning and execution cycle.

Instead of returning one static answer, the model:

1.  Receives the user's goal.
2.  Determines what information or action is required.
3.  Requests an available tool when needed.
4.  The Python agent executes that tool.
5.  The execution result is returned to the model.
6.  The model evaluates the result and decides what to do next.
7.  The cycle continues until the task is completed or the iteration
    limit is reached.

This creates a practical **reason → execute → observe → correct**
workflow.

------------------------------------------------------------------------

## 🛡️ Sandboxed Tool Execution

All tools are restricted to the **project root directory**.

The agent cannot use path traversal such as `..` to access files outside
the workspace.

### Available Tools

  -----------------------------------------------------------------------
  Tool                                Purpose
  ----------------------------------- -----------------------------------
  `list_files(path=".")`              Lists files and directories inside
                                      project-relative paths

  `read_file(path)`                   Reads text files inside the project
                                      workspace

  `write_file(path, content)`         Creates or updates text files
                                      inside the workspace

  `run_python_test(path)`             Runs Python test files using the
                                      project's virtual-environment
                                      interpreter
  -----------------------------------------------------------------------

### Security Controls

-   Project-root sandboxing
-   Path traversal protection
-   No access to files outside the workspace
-   Non-existent path validation
-   Python execution through `sys.executable`
-   Captured stdout, stderr, and exit codes
-   `shell=True` is not used for test execution
-   File writing does not delete existing files

------------------------------------------------------------------------

## 🧠 How Qwen Selects Tools

The agent provides Qwen with the conversation history and the available
tool definitions.

When Qwen determines that an action is required, it can return a
structured tool request through:

-   Native Ollama tool-call schemas, or
-   JSON tool-call blocks

The agent loop parses the request, extracts the tool parameters, and
dispatches the corresponding Python function implemented in `tools.py`.

------------------------------------------------------------------------

## 🔄 How Tool Results Return to Qwen

After a tool is executed, its result is converted into a message with
role:

``` text
tool
```

The result is appended to the conversation context and returned to Qwen.

Depending on the tool, the model can receive information such as:

-   Directory listings
-   File contents
-   Test output
-   Standard error
-   Process exit codes

Qwen then uses this empirical feedback to determine the next action.

This feedback loop is what allows the agent to **inspect → modify → test
→ verify** instead of simply guessing a solution.

------------------------------------------------------------------------

# 🧪 Bug-Fix / Self-Healing Demo

The included demo uses a deliberately broken calculator implementation
to demonstrate the complete agent loop.

The agent is expected to:

1.  Inspect the project files.
2.  Identify the relevant calculator implementation.
3.  Inspect the failing test.
4.  Diagnose the defect.
5.  Modify the implementation.
6.  Run the test through the provided tool.
7.  Analyze the test result.
8.  Return the final outcome.

### Demo Flow

``` text
Failing Test
     │
     ▼
Agent inspects workspace
     │
     ▼
Reads calculator + test
     │
     ▼
Identifies incorrect implementation
     │
     ▼
Writes corrected implementation
     │
     ▼
Runs test
     │
     ▼
Test Result
     │
     ▼
Agent verifies the fix
```

------------------------------------------------------------------------

## ⚙️ Prerequisites

-   Windows OS
-   Python **3.14+**
-   Ollama installed and running locally
-   Ollama available at:

``` text
http://localhost:11434
```

-   Qwen2.5-Coder model:

``` text
qwen2.5-coder:1.5b
```

-   Project virtual environment with the `ollama` Python package
    installed

------------------------------------------------------------------------

## 📦 Setup

### 1. Clone the repository

``` powershell
git clone https://github.com/pbhandari07/Agent_AI_Infrastucture-.git
cd Agent_AI_Infrastucture-/terraform-self-healing-agent
```

### 2. Activate the virtual environment

``` powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Make sure Ollama is running

Verify that the local Ollama service is available at:

``` text
http://localhost:11434
```

### 4. Pull the model

``` powershell
ollama pull qwen2.5-coder:1.5b
```

### 5. Test the Ollama connection

``` powershell
python test_ollama.py
```

------------------------------------------------------------------------

# ▶️ Running the Demo

## Step 1 --- Confirm the initial failure

Run the test independently:

``` powershell
python demo/test_buggy_calculator.py
```

The initial implementation is intentionally incorrect.

Expected failure:

``` text
AssertionError: -1 != 5
```

------------------------------------------------------------------------

## Step 2 --- Start the AI agent

``` powershell
python agent.py
```

The agent will:

-   Inspect the workspace
-   Read the relevant files
-   Identify the defect in `demo/buggy_calculator.py`
-   Modify the implementation
-   Execute the test using the sandboxed test tool
-   Analyze the result
-   Produce the final response

------------------------------------------------------------------------

## Step 3 --- Verify the fix independently

Run the test again:

``` powershell
python demo/test_buggy_calculator.py
```

Expected result:

``` text
Ran 4 tests ... OK
```

The independent test run provides a final verification outside the
agent's reasoning loop.

------------------------------------------------------------------------

# 📁 Project Structure

A simplified view of the project:

``` text
terraform-self-healing-agent/
│
├── agent.py
├── tools.py
├── test_ollama.py
├── demo/
│   ├── buggy_calculator.py
│   └── test_buggy_calculator.py
│
└── .venv/
```

> `.venv/` is a local Python virtual environment and should normally be
> excluded from version control using `.gitignore`.

------------------------------------------------------------------------

# 🔐 Why Sandboxing Matters

An AI agent capable of reading and modifying files needs explicit
boundaries.

This project therefore treats the workspace as a controlled execution
environment.

The tool layer validates paths before performing file operations,
preventing the agent from escaping the project root.

This is particularly important when extending the architecture toward
DevOps use cases, where an autonomous agent could potentially interact
with infrastructure configuration.

------------------------------------------------------------------------

# ☁️ DevOps / Terraform Extension

The current implementation focuses on the agentic **tool-use and
self-healing pattern**.

The architecture can be extended toward Terraform workflows such as:

``` text
Terraform Configuration
        │
        ▼
   Agent Inspection
        │
        ▼
 terraform validate
        │
        ├── PASS ──► Continue
        │
        ▼
      ERROR
        │
        ▼
 AI Diagnosis
        │
        ▼
 Controlled File Modification
        │
        ▼
 terraform validate
        │
        ▼
 Verification
```

Potential future extensions include:

-   Terraform configuration inspection
-   `terraform fmt`
-   `terraform validate`
-   Terraform plan analysis
-   Detection of common configuration errors
-   Controlled remediation suggestions
-   Policy/compliance checks
-   Infrastructure drift analysis
-   Human approval before infrastructure-changing operations
-   Integration with CI/CD pipelines

> **Important:** Infrastructure-changing operations should remain
> explicitly controlled and should not be granted unrestricted
> autonomous execution.

------------------------------------------------------------------------

# 🧰 Technology Stack

  Category                   Technology
  -------------------------- -----------------------------------------
  Language                   Python
  LLM Runtime                Ollama
  AI Model                   Qwen2.5-Coder 1.5B
  Agent Pattern              Tool-Using / Iterative Agent Loop
  Infrastructure Direction   Terraform
  Execution                  Python subprocess / virtual environment
  Testing                    Python `unittest` workflow
  Platform                   Windows

------------------------------------------------------------------------

# 🎯 Key Engineering Concepts

This project demonstrates practical concepts around:

-   Agentic AI
-   Local LLMs
-   Tool calling
-   Structured execution
-   Feedback-driven reasoning
-   Automated remediation
-   Workspace sandboxing
-   Safe file operations
-   Test-driven verification
-   DevOps automation
-   Infrastructure self-healing concepts

------------------------------------------------------------------------

## 🚧 Future Improvements

Planned directions for evolving the project include:

-   [ ] Terraform-specific tools
-   [ ] `terraform fmt` / `validate` integration
-   [ ] Terraform plan analysis
-   [ ] Azure infrastructure diagnostics
-   [ ] Azure Monitor / Log Analytics integration
-   [ ] CI/CD integration
-   [ ] Human-in-the-loop approval gates
-   [ ] More granular tool permissions
-   [ ] Audit logging for agent actions
-   [ ] Containerized execution
-   [ ] Policy and compliance validation

------------------------------------------------------------------------

## 👨‍💻 Author

**Pankaj Bhandari**

Cloud & DevOps Engineer specializing in:

-   Microsoft Azure
-   Terraform / Infrastructure as Code
-   CI/CD Automation
-   Cloud Security
-   Governance & FinOps
-   DevOps Automation
-   AI-enabled cloud workloads

------------------------------------------------------------------------

## ⭐ Project Goal

The goal of this project is to explore how **local AI agents can safely
interact with development and infrastructure tooling** to create
feedback-driven automation and self-healing workflows.

The emphasis is on combining **LLM reasoning + controlled tools +
empirical verification**, rather than allowing an AI model to make
unrestricted changes.

