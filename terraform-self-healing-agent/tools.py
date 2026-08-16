"""
Sandboxed tools for the local self-healing agent.

All file operations are restricted to the project root directory.
Terraform operations are restricted to demo/terraform.

The approved tools are:
- list_files(path)
- read_file(path)
- write_file(path, content)
- terraform_init(path)
- terraform_fmt(path)
- terraform_validate(path)
- terraform_plan(path)

The agent CANNOT run terraform apply or destroy infrastructure.
"""

import sys
import re
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


# ============================================================
# PATH SECURITY
# ============================================================

def validate_path(path_str: str) -> Path:
    """
    Validate and resolve a path relative to PROJECT_ROOT.

    Prevents access outside the project directory.
    """
    if not path_str or not isinstance(path_str, str):
        raise ValueError("Invalid path string provided.")

    target = (PROJECT_ROOT / path_str).resolve()

    try:
        target.relative_to(PROJECT_ROOT)
    except ValueError:
        raise ValueError(
            f"Security Error: Access denied. "
            f"Path '{path_str}' is outside project root."
        )

    return target


def terraform_directory(path: str = "demo/terraform") -> Path:
    """
    Validate that a Terraform operation is restricted to
    the demo/terraform directory.
    """
    if not path or path == "." or path == "":
        path = "demo/terraform"

    target = validate_path(path)
    allowed_dir = (PROJECT_ROOT / "demo" / "terraform").resolve()

    if target != allowed_dir:
        raise ValueError(
            "Security Error: Terraform operations are restricted "
            "to 'demo/terraform'."
        )

    if not target.exists():
        raise ValueError(
            f"Error: Terraform directory '{path}' does not exist."
        )

    if not target.is_dir():
        raise ValueError(
            f"Error: Terraform path '{path}' is not a directory."
        )

    return target


# ============================================================
# FILE TOOLS
# ============================================================

def list_files(path: str = ".") -> str:
    """
    List files and directories inside the specified project-relative path.
    """
    try:
        target = validate_path(path)

        if not target.exists():
            return f"Error: Path '{path}' does not exist."

        if not target.is_dir():
            return f"Error: Path '{path}' is a file, not a directory."

        items = []

        for item in sorted(target.iterdir()):
            rel = item.relative_to(PROJECT_ROOT)

            if item.is_dir():
                prefix = "[DIR] "
            else:
                prefix = "[FILE]"

            items.append(f"{prefix} {rel.as_posix()}")

        if not items:
            return f"Directory '{path}' is empty."

        return "\n".join(items)

    except Exception as e:
        return f"Error: {e}"


def read_file(path: str) -> str:
    """
    Read the contents of a file inside the project root.
    """
    try:
        target = validate_path(path)

        if not target.exists():
            return f"Error: File '{path}' does not exist."

        if not target.is_file():
            return f"Error: Path '{path}' is a directory, not a file."

        return target.read_text(encoding="utf-8")

    except Exception as e:
        return f"Error: {e}"


def write_file(path: str, content: str) -> str:
    """
    Write or update a text file inside the project root.

    This tool never deletes files.
    """
    try:
        target = validate_path(path)

        if not isinstance(content, str):
            return "Error: File content must be a string."

        # Block writing to internal .terraform hidden files or error logs
        normalized_parts = target.relative_to(PROJECT_ROOT).parts
        if ".terraform" in normalized_parts:
            return (
                "ERROR: Cannot modify internal .terraform files. "
                "You must edit the actual Terraform configuration file (e.g. demo/terraform/main.tf)."
            )

        if path.endswith(".tf"):
            content = re.sub(r"^```(?:hcl|terraform)?\s*\n?", "", content, flags=re.IGNORECASE)
            content = re.sub(r"\n?```\s*$", "", content)
            clean_str = content.strip()
            if clean_str.startswith("<") or "tool_response" in clean_str or "tool_call" in clean_str:
                return (
                    "ERROR: Invalid Terraform HCL content. "
                    "Do NOT write tool tags or XML markup to .tf files."
                )
            if len(clean_str) < 50:
                return (
                    f"ERROR: Partial HCL code fragment rejected ({len(clean_str)} characters). "
                    f"write_file replaces the ENTIRE file. You must provide the COMPLETE file content for "
                    f"'{path}' including all terraform, provider, variable, and resource blocks."
                )
            if 'provider "hashicorp/' in clean_str or 'provider "registry.terraform.io/' in clean_str or 'provider "hascorp/' in clean_str:
                return (
                    "ERROR: Invalid HCL provider block syntax. "
                    "In Terraform HCL, provider blocks must use only the simple local name, like:\n"
                    "provider \"azurerm\" {\n"
                    "  features {}\n"
                    "}\n"
                    "Do NOT write slash paths in provider block headers."
                )

        if target.exists() and target.is_file():
            try:
                existing_content = target.read_text(encoding="utf-8")
                if existing_content == content:
                    return (
                        f"ERROR: File '{path}' already contains this exact content. "
                        "You wrote identical content without fixing any typos! "
                        "Do NOT call write_file with identical content. "
                        "Read the error output and main.tf carefully, locate the exact spelling/syntax error, and provide the corrected file content."
                    )
            except Exception:
                pass

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        return (
            f"Success: Wrote {len(content)} characters "
            f"to '{path}'."
        )

    except Exception as e:
        return f"Error: {e}"



# ============================================================
# TERRAFORM INIT
# ============================================================

def terraform_init(path: str = "demo/terraform") -> str:
    """
    Run terraform init inside the allowed Terraform directory.

    This does NOT run terraform apply.
    """
    try:
        target = terraform_directory(path)

        result = subprocess.run(
            [
                "terraform",
                "init",
                "-input=false",
            ],
            cwd=str(target),
            capture_output=True,
            text=True,
            timeout=120,
        )

        output = []

        if result.stdout:
            output.append(
                f"STDOUT:\n{result.stdout.strip()}"
            )

        if result.stderr:
            output.append(
                f"STDERR:\n{result.stderr.strip()}"
            )

        status = (
            "PASSED"
            if result.returncode == 0
            else f"FAILED (Exit Code {result.returncode})"
        )

        output.append(f"Status: {status}")

        return "\n".join(output)

    except subprocess.TimeoutExpired:
        return "Error: Terraform init timed out after 120 seconds."

    except Exception as e:
        return f"Error: {e}"


# ============================================================
# TERRAFORM FORMAT
# ============================================================

def terraform_fmt(path: str = "demo/terraform") -> str:
    """
    Run terraform fmt recursively inside the allowed Terraform directory.
    """
    try:
        target = terraform_directory(path)

        result = subprocess.run(
            [
                "terraform",
                "fmt",
                "-recursive",
            ],
            cwd=str(target),
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = []

        if result.stdout:
            output.append(
                f"STDOUT:\n{result.stdout.strip()}"
            )

        if result.stderr:
            output.append(
                f"STDERR:\n{result.stderr.strip()}"
            )

        status = (
            "PASSED"
            if result.returncode == 0
            else f"FAILED (Exit Code {result.returncode})"
        )

        output.append(f"Status: {status}")

        return "\n".join(output)

    except subprocess.TimeoutExpired:
        return "Error: Terraform fmt timed out after 30 seconds."

    except Exception as e:
        return f"Error: {e}"


# ============================================================
# TERRAFORM VALIDATE
# ============================================================

def terraform_validate(path: str = "demo/terraform") -> str:
    """
    Run terraform validate inside the allowed Terraform directory.
    """
    try:
        target = terraform_directory(path)

        result = subprocess.run(
            [
                "terraform",
                "validate",
            ],
            cwd=str(target),
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = []

        if result.stdout:
            output.append(
                f"STDOUT:\n{result.stdout.strip()}"
            )

        if result.stderr:
            output.append(
                f"STDERR:\n{result.stderr.strip()}"
            )

        status = (
            "PASSED"
            if result.returncode == 0
            else f"FAILED (Exit Code {result.returncode})"
        )

        output.append(f"Status: {status}")

        return "\n".join(output)

    except subprocess.TimeoutExpired:
        return "Error: Terraform validate timed out after 30 seconds."

    except Exception as e:
        return f"Error: {e}"


# ============================================================
# TERRAFORM PLAN
# ============================================================

def terraform_plan(path: str = "demo/terraform") -> str:
    """
    Run terraform plan inside the allowed Terraform directory.

    IMPORTANT:
    This tool only runs terraform plan.
    It NEVER runs terraform apply or terraform destroy.
    """
    try:
        target = terraform_directory(path)

        result = subprocess.run(
            [
                "terraform",
                "plan",
                "-input=false",
            ],
            cwd=str(target),
            capture_output=True,
            text=True,
            timeout=120,
        )

        output = []

        if result.stdout:
            output.append(
                f"STDOUT:\n{result.stdout.strip()}"
            )

        if result.stderr:
            output.append(
                f"STDERR:\n{result.stderr.strip()}"
            )

        status = (
            "PASSED"
            if result.returncode == 0
            else f"FAILED (Exit Code {result.returncode})"
        )

        output.append(f"Status: {status}")

        return "\n".join(output)

    except subprocess.TimeoutExpired:
        return "Error: Terraform plan timed out after 120 seconds."

    except Exception as e:
        return f"Error: {e}"


# ============================================================
# OLLAMA TOOL SCHEMAS
# ============================================================

TOOLS = [

    # --------------------------------------------------------
    # LIST FILES
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "List files and directories inside the "
                "specified project-relative path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Relative directory path inside "
                            "project root."
                        ),
                    },
                },
                "required": ["path"],
            },
        },
    },

    # --------------------------------------------------------
    # READ FILE
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the text contents of a file inside "
                "the project root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Relative file path inside project root."
                        ),
                    },
                },
                "required": ["path"],
            },
        },
    },

    # --------------------------------------------------------
    # WRITE FILE
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write or update a text file inside the project root. "
                "Never deletes files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Relative file path inside project root."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "Exact text content to write to the file."
                        ),
                    },
                },
                "required": ["path", "content"],
            },
        },
    },


    # --------------------------------------------------------
    # TERRAFORM INIT
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "terraform_init",
            "description": (
                "Run terraform init inside the demo/terraform "
                "sandbox directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Terraform directory. "
                            "Use demo/terraform."
                        ),
                    },
                },
                "required": [],
            },
        },
    },

    # --------------------------------------------------------
    # TERRAFORM FMT
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "terraform_fmt",
            "description": (
                "Run terraform fmt -recursive inside "
                "the demo/terraform sandbox directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Terraform directory. "
                            "Use demo/terraform."
                        ),
                    },
                },
                "required": [],
            },
        },
    },

    # --------------------------------------------------------
    # TERRAFORM VALIDATE
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "terraform_validate",
            "description": (
                "Run terraform validate inside the "
                "demo/terraform sandbox directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Terraform directory. "
                            "Use demo/terraform."
                        ),
                    },
                },
                "required": [],
            },
        },
    },

    # --------------------------------------------------------
    # TERRAFORM PLAN
    # --------------------------------------------------------

    {
        "type": "function",
        "function": {
            "name": "terraform_plan",
            "description": (
                "Run terraform plan inside the "
                "demo/terraform sandbox directory. "
                "Never run terraform apply."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Terraform directory. "
                            "Use demo/terraform."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
]


# ============================================================
# TOOL MAP
# ============================================================

TOOL_MAP = {
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,

    "terraform_init": terraform_init,
    "terraform_fmt": terraform_fmt,
    "terraform_validate": terraform_validate,
    "terraform_plan": terraform_plan,
}