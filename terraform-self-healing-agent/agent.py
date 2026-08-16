"""
Local Terraform Self-Healing Agent.

The agent:
- Inspects Terraform files
- Runs terraform init
- Runs terraform fmt
- Runs terraform validate
- Detects validation errors
- Fixes required Terraform files
- Re-runs active stage until it passes
- Runs terraform plan
- NEVER runs terraform apply
- NEVER destroys infrastructure
"""

import json
import re

import llm
import tools


MAX_ITERATIONS = 20


SYSTEM_PROMPT = """You are an autonomous Terraform self-healing agent for demo/terraform.

YOUR OBJECTIVE:
Inspect and self-heal the Terraform configuration located in demo/terraform until 'terraform plan' passes successfully.

STRICT STAGE-GATED WORKFLOW:
You must process Terraform execution in 4 strict sequential stages:
1. terraform_init(path="demo/terraform")
2. terraform_fmt(path="demo/terraform")
3. terraform_validate(path="demo/terraform")
4. terraform_plan(path="demo/terraform")

FIRST ACTION:
Execute stage command terraform_init(path="demo/terraform") first.

GENERIC DIAGNOSTIC & HCL SPECIFICATION RULES:
1. Required Providers & String Literals:
   - Provider sources in required_providers must strictly follow "namespace/provider_name" format (e.g. "hashicorp/azurerm", "hashicorp/aws").
   - Provider namespaces and provider names contain only lowercase alphanumeric characters, hyphens, and underscores, separated by a single forward slash ('/').
   - If a provider source string literal contains accidental spaces, tabs, linebreaks, or fragmented words (e.g. "hashicor   p/azure   rm"), clean up all internal spaces and fragmentation to restore the valid alphanumeric "namespace/provider_name" identifier without guessing arbitrary extra path components or truncated subdirectories.
2. Variable Blocks:
   - Syntax: variable "name" { type = ... default = ... description = ... }
   - Inside a variable block, NEVER use custom attributes like 'name = ...', 'location = ...', or resource property names. To assign default values in a variable block, ALWAYS use 'default = "..."'.
   - Variable types must be valid HCL types (string, number, bool, list, map, object, any).
3. Resource Blocks:
   - Resource syntax: resource "resource_type" "name" { attribute = value }
   - Ensure all resource argument names match valid provider resource schemas, and variable references use 'var.variable_name'.
4. Self-Correction & Progress:
   - Line-by-line inspect every block in main.tf. If your previous write_file call produced a string error or was rejected, analyze the exact string differences, identify why the repair failed, and output a genuinely corrected valid HCL file.

FOR EVERY STAGE:
1. Execute the active stage command (e.g. terraform_init, terraform_fmt, etc.).
2. If the command succeeds (Status: PASSED), immediately move to the next stage.
3. If the command fails (Status: FAILED):
   a. Read the official Terraform error output (STDOUT/STDERR) carefully.
   b. Review the current file content provided in the message.
   c. Line-by-line inspect the relevant block to locate malformed provider sources, typos, invalid attributes, broken variable references, or syntax errors.
   d. Call write_file(path="demo/terraform/main.tf", content=...) with the COMPLETE, fully repaired Terraform HCL file content.
   e. Re-run the SAME stage command to verify if it passes.
4. Do NOT advance to the next stage until the current active stage returns Status: PASSED.

RULES:
- write_file replaces the ENTIRE file. Always pass the COMPLETE main.tf content with all blocks (terraform, provider, variable, resource).
- NEVER write single line snippets, tool tags, XML markup, or markdown code fences into .tf files.
- NEVER create internal error files like errors.txt or modify .terraform directories. Always edit the actual .tf file (demo/terraform/main.tf).
- NEVER execute terraform apply or destroy infrastructure.
"""


def parse_native_tool_call(tool_call):
    """
    Extract tool name and arguments from an Ollama native ToolCall
    or dictionary representation.
    """
    if hasattr(tool_call, "function"):
        function = tool_call.function
        name = getattr(function, "name", None)
        arguments = getattr(function, "arguments", None)
        if arguments is None:
            arguments = getattr(function, "args", {})
        return name, arguments

    if isinstance(tool_call, dict) and "function" in tool_call:
        function = tool_call["function"]
        name = function.get("name")
        arguments = (
            function.get("arguments")
            or function.get("args")
            or {}
        )
        return name, arguments

    return None, {}


def normalize_arguments(arguments):
    """
    Convert tool arguments into a Python dictionary.
    """
    if arguments is None:
        return {}

    if isinstance(arguments, dict):
        return arguments

    if isinstance(arguments, str):
        arguments = arguments.strip()
        if not arguments:
            return {}

        try:
            parsed = json.loads(arguments)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}

    return {}


def extract_tool_calls(message):
    """
    Extract tool calls from:
    1. Native Ollama tool_calls
    2. JSON tool-call text
    3. Pythonic tool call text (e.g. terraform_init(path="demo/terraform"))
    4. Markdown code-blocks or HCL blocks containing Terraform code
    """
    native_calls = getattr(message, "tool_calls", None)
    if native_calls is None and isinstance(message, dict):
        native_calls = message.get("tool_calls")

    if native_calls:
        parsed_calls = []
        for tool_call in native_calls:
            name, arguments = parse_native_tool_call(tool_call)
            if name:
                arguments = normalize_arguments(arguments)
                parsed_calls.append((name, arguments))
        if parsed_calls:
            return parsed_calls

    content = getattr(message, "content", "")
    if not content and isinstance(message, dict):
        content = message.get("content", "")
    if not content:
        return []

    content = str(content).strip()

    # Direct JSON tool call
    try:
        if content.startswith("{") and content.endswith("}"):
            data = json.loads(content)
            name = (
                data.get("name")
                or data.get("tool")
                or data.get("function")
            )
            arguments = (
                data.get("arguments")
                or data.get("args")
                or data.get("parameters")
                or {}
            )
            if name:
                return [(name, normalize_arguments(arguments))]
    except Exception:
        pass

    # Embedded JSON tool call
    pattern = (
        r'\{\s*'
        r'"(?:name|tool|function)"\s*:\s*"([^"]+)"\s*,\s*'
        r'"(?:arguments|args|parameters)"\s*:\s*'
        r'(\{.*?\})'
        r'\s*\}'
    )
    match = re.search(pattern, content, re.DOTALL)
    if match:
        name = match.group(1)
        arguments_raw = match.group(2)
        try:
            arguments = json.loads(arguments_raw)
            return [(name, normalize_arguments(arguments))]
        except Exception:
            pass

    # Pythonic tool call syntax e.g. terraform_init(path="demo/terraform")
    func_call_match = re.search(
        r'(terraform_init|terraform_fmt|terraform_validate|terraform_plan|read_file|list_files)\s*\(\s*(?:path\s*=\s*)?["\']?([^"\')]+)?["\']?\s*\)',
        content,
        re.IGNORECASE,
    )
    if func_call_match:
        fn_name = func_call_match.group(1).lower()
        target_p = func_call_match.group(2) or "demo/terraform"
        return [(fn_name, {"path": target_p.strip()})]

    # Markdown code block or HCL block containing Terraform code
    code_match = re.search(
        r"```(?:hcl|terraform)?\s*\n(.*?)```",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    hcl_code = None
    if code_match:
        hcl_code = code_match.group(1).strip()
    elif "terraform {" in content or 'provider "' in content or 'resource "' in content:
        hcl_code = content.strip()

    if hcl_code and len(hcl_code) > 30 and not hcl_code.startswith("<") and "tool_response" not in hcl_code:
        path_match = re.search(r"(?:demo/terraform/)?[A-Za-z0-9_.-]+\.tf", content)
        target_path = path_match.group(0) if path_match else "demo/terraform/main.tf"
        if not target_path.startswith("demo/terraform/"):
            target_path = "demo/terraform/" + target_path

        return [("write_file", {"path": target_path, "content": hcl_code})]

    return []


def tool_result_passed(result):
    """
    Determine whether a tool result reports success.
    """
    if not result:
        return False
    text = str(result)
    return "Status: PASSED" in text or "Success!" in text


def run_agent(
    goal: str,
    max_iterations: int = MAX_ITERATIONS,
):
    """
    Main autonomous agent loop with stage-gated self-healing execution.
    """
    print("=" * 70, flush=True)
    print("[AGENT] Initializing Terraform self-healing agent", flush=True)
    print(f"[AGENT] Goal:\n{goal}", flush=True)
    print("=" * 70, flush=True)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": goal,
        },
    ]

    iteration = 0
    tools_called_count = 0

    STAGES = ["terraform_init", "terraform_fmt", "terraform_validate", "terraform_plan"]
    current_stage_idx = 0

    terraform_init_passed = False
    terraform_fmt_passed = False
    terraform_validate_passed = False
    terraform_plan_passed = False

    stage_results = {
        "terraform_init": "NOT RUN",
        "terraform_fmt": "NOT RUN",
        "terraform_validate": "NOT RUN",
        "terraform_plan": "NOT RUN",
    }

    errors_found = []
    files_changed = set()
    fixes_made = []

    last_tool_signature = None
    consecutive_duplicate_count = 0

    while iteration < max_iterations:
        iteration += 1
        active_stage = STAGES[min(current_stage_idx, len(STAGES) - 1)]

        print(
            f"\n[AGENT] --- Iteration {iteration}/{max_iterations} (Active Stage: {active_stage}) ---",
            flush=True,
        )

        try:
            print("[AGENT] Contacting local Ollama LLM...", flush=True)
            response = llm.chat(messages=messages, tools=tools.TOOLS)
            message = response.message
        except Exception as exc:
            print("\n[AGENT ERROR]", flush=True)
            print(str(exc), flush=True)
            return {
                "success": False,
                "iterations": iteration,
                "tool_calls_count": tools_called_count,
                "final_answer": str(exc),
            }

        tool_calls = extract_tool_calls(message)

        if not tool_calls:
            content = getattr(message, "content", "")
            if not content and isinstance(message, dict):
                content = message.get("content", "")
            content = str(content or "").strip()

            if current_stage_idx < len(STAGES):
                reminder = (
                    f"Stage '{active_stage}' has not passed yet.\n"
                    f"Do NOT provide a text summary yet.\n"
                    f"Execute '{active_stage}(path=\"demo/terraform\")' or call write_file to repair demo/terraform/main.tf."
                )
                print("\n[AGENT] Model attempted text response without tool call. Sending stage directive...", flush=True)
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": reminder})
                continue

            print("\n[FINAL ANSWER]", flush=True)
            print(content, flush=True)
            print("=" * 70, flush=True)
            return {
                "success": terraform_plan_passed,
                "iterations": iteration,
                "tool_calls_count": tools_called_count,
                "final_answer": content,
            }

        messages.append(message)

        for function_name, function_args in tool_calls:
            tools_called_count += 1
            function_args = normalize_arguments(function_args)

            tool_sig = (function_name, json.dumps(function_args, sort_keys=True))
            if tool_sig == last_tool_signature:
                consecutive_duplicate_count += 1
            else:
                last_tool_signature = tool_sig
                consecutive_duplicate_count = 1

            if consecutive_duplicate_count >= 3:
                warning = (
                    f"ANTI-LOOP ALERT: Tool '{function_name}' was executed 3 times consecutively "
                    "with identical arguments without progress.\n"
                    "Stop repeating identical tool calls! Re-read the latest Terraform error output carefully, "
                    "locate the exact typo/mistake in 'demo/terraform/main.tf', correct it, and call write_file with updated HCL content."
                )
                print(f"\n[AGENT WARNING] {warning}", flush=True)
                messages.append({
                    "role": "tool",
                    "name": function_name,
                    "content": warning,
                })
                continue

            if function_name not in tools.TOOL_MAP:
                error_message = f"Error: Tool '{function_name}' is not recognized or permitted."
                print(f"[TOOL RESULT]\n{error_message}", flush=True)
                messages.append({
                    "role": "tool",
                    "name": function_name,
                    "content": error_message,
                })
                continue

            if function_name in STAGES:
                requested_idx = STAGES.index(function_name)
                if requested_idx > current_stage_idx:
                    gate_error = (
                        f"ERROR: Cannot run '{function_name}'. Stage '{STAGES[current_stage_idx]}' "
                        f"is currently active and has NOT passed yet. You must re-run '{STAGES[current_stage_idx]}' "
                        f"and fix all errors until it passes before advancing."
                    )
                    print(f"[TOOL RESULT]\n{gate_error}", flush=True)
                    messages.append({
                        "role": "tool",
                        "name": function_name,
                        "content": gate_error,
                    })
                    continue

            if function_name == "write_file" and stage_results[active_stage] == "NOT RUN":
                pre_run_err = (
                    f"ERROR: You must execute active stage command '{active_stage}(path=\"demo/terraform\")' first "
                    "to obtain official Terraform compiler diagnostics before modifying files."
                )
                print(f"[TOOL RESULT]\n{pre_run_err}", flush=True)
                messages.append({
                    "role": "tool",
                    "name": function_name,
                    "content": pre_run_err,
                })
                continue

            try:
                tool_function = tools.TOOL_MAP[function_name]
                result_string = str(tool_function(**function_args))
            except Exception as exc:
                result_string = f"Error executing tool '{function_name}': {exc}"

            print(f"[TOOL RESULT]\n{result_string.strip()}", flush=True)

            if function_name in STAGES:
                passed = tool_result_passed(result_string)
                stage_results[function_name] = "PASSED" if passed else "FAILED"

                if function_name == "terraform_init":
                    terraform_init_passed = passed
                elif function_name == "terraform_fmt":
                    terraform_fmt_passed = passed
                elif function_name == "terraform_validate":
                    terraform_validate_passed = passed
                elif function_name == "terraform_plan":
                    terraform_plan_passed = passed

                if passed:
                    if STAGES.index(function_name) == current_stage_idx:
                        current_stage_idx += 1
                        if current_stage_idx < len(STAGES):
                            next_stage = STAGES[current_stage_idx]
                            prompt_msg = (
                                f"[TOOL RESULT for '{function_name}']:\n{result_string}\n\n"
                                f"[SYSTEM DIRECTIVE]: Stage '{function_name}' PASSED! Immediately execute the next stage: {next_stage}(path='demo/terraform') now."
                            )
                        else:
                            report = (
                                "======================================================================\n"
                                "              TERRAFORM SELF-HEALING WORKFLOW REPORT\n"
                                "======================================================================\n"
                                "1. Errors Found & Handled:\n"
                                + ("\n".join(f"   - {err}" for err in errors_found) if errors_found else "   - None\n")
                                + f"\n2. Files Changed:\n"
                                + ("\n".join(f"   - {f}" for f in files_changed) if files_changed else "   - None\n")
                                + f"\n3. Fixes Made:\n"
                                + ("\n".join(f"   - {fix}" for fix in fixes_made) if fixes_made else "   - None\n")
                                + f"\n4. Terraform Stage Results:\n"
                                + f"   - terraform init    : {stage_results['terraform_init']}\n"
                                + f"   - terraform fmt     : {stage_results['terraform_fmt']}\n"
                                + f"   - terraform validate: {stage_results['terraform_validate']}\n"
                                + f"   - terraform plan    : {stage_results['terraform_plan']}\n"
                                + "======================================================================"
                            )
                            print("\n[FINAL ANSWER]\n" + report, flush=True)
                            messages.append({"role": "user", "content": f"[TOOL RESULT for '{function_name}']:\n{result_string}\n\n{report}"})
                            return {
                                "success": True,
                                "iterations": iteration,
                                "tool_calls_count": tools_called_count,
                                "final_answer": report,
                            }
                    else:
                        prompt_msg = f"[TOOL RESULT for '{function_name}']:\n{result_string}"
                else:
                    err_snippet = result_string.strip().split("\n")[0]
                    errors_found.append(f"Stage '{function_name}': {err_snippet}")
                    curr_tf_content = tools.read_file("demo/terraform/main.tf")
                    prompt_msg = (
                        f"[TOOL RESULT for '{function_name}']:\n{result_string}\n\n"
                        f"[CURRENT CONTENT OF demo/terraform/main.tf]:\n```hcl\n{curr_tf_content}\n```\n\n"
                        f"[SYSTEM DIRECTIVE]: Stage '{function_name}' FAILED with the compiler error above.\n"
                        f"Read the error output and current file content carefully, locate ALL mistakes in 'demo/terraform/main.tf', "
                        f"and call write_file(path='demo/terraform/main.tf', content=...) with the COMPLETE repaired HCL file containing all blocks (terraform, provider, variable, resource)."
                    )

                messages.append({"role": "user", "content": prompt_msg})

            elif function_name == "write_file":
                if "Success:" in result_string:
                    target_p = function_args.get("path", "")
                    files_changed.add(target_p)
                    curr_stage_name = STAGES[min(current_stage_idx, len(STAGES) - 1)]
                    fixes_made.append(f"Updated '{target_p}' to resolve stage '{curr_stage_name}' errors.")
                    prompt_msg = (
                        f"[TOOL RESULT for 'write_file']:\n{result_string}\n\n"
                        f"[SYSTEM DIRECTIVE]: File '{target_p}' updated! Now immediately re-run stage '{curr_stage_name}(path=\"demo/terraform\")' to verify if stage '{curr_stage_name}' passes."
                    )
                else:
                    curr_tf_content = tools.read_file("demo/terraform/main.tf")
                    prompt_msg = (
                        f"[TOOL RESULT for 'write_file']:\n{result_string}\n\n"
                        f"[CURRENT CONTENT OF demo/terraform/main.tf]:\n```hcl\n{curr_tf_content}\n```\n\n"
                        f"[SYSTEM DIRECTIVE]: Your write_file attempt was rejected because the content was identical to the current file without fixing any errors.\n"
                        f"Re-read the compiler output and current file content above. Check for invalid block attributes (e.g. 'name' or 'location' inside variable blocks instead of 'default'), provider typos (e.g. 'hashcorp' -> 'hashicorp'), invalid type names, or bad variable references. Produce a genuinely modified complete HCL file."
                    )
                messages.append({"role": "user", "content": prompt_msg})

            else:
                messages.append({
                    "role": "user",
                    "content": f"[TOOL RESULT for '{function_name}']:\n{result_string}",
                })

    # ---------------------------------------------------------
    # Maximum iterations reached
    # ---------------------------------------------------------
    terraform_init_passed = (stage_results.get("terraform_init") == "PASSED")
    terraform_fmt_passed = (stage_results.get("terraform_fmt") == "PASSED")
    terraform_validate_passed = (stage_results.get("terraform_validate") == "PASSED")
    terraform_plan_passed = (stage_results.get("terraform_plan") == "PASSED")

    print("\n[AGENT] Maximum iteration limit reached.", flush=True)
    print(f"[AGENT] Iterations: {iteration}", flush=True)
    print(f"[AGENT] Tool calls: {tools_called_count}", flush=True)
    print(f"[AGENT] Terraform init passed: {terraform_init_passed}", flush=True)
    print(f"[AGENT] Terraform fmt passed: {terraform_fmt_passed}", flush=True)
    print(f"[AGENT] Terraform validate passed: {terraform_validate_passed}", flush=True)
    print(f"[AGENT] Terraform plan passed: {terraform_plan_passed}", flush=True)

    return {
        "success": terraform_plan_passed,
        "iterations": iteration,
        "tool_calls_count": tools_called_count,
        "final_answer": "Maximum iterations reached.",
    }


if __name__ == "__main__":
    terraform_goal = (
        "Inspect and self-heal the Terraform project located at demo/terraform "
        "until 'terraform plan' passes successfully."
    )
    run_agent(terraform_goal)