"""
LLM Interface module for communicating with local Ollama model.
"""

import sys
import ollama

MODEL_NAME = "qwen2.5-coder:1.5b"

def chat(messages: list, tools: list = None):
    """
    Send messages to the local Ollama instance with optional tools.
    
    Args:
        messages: List of message dictionaries (role, content, tool_calls, etc.).
        tools: Optional list of python functions or tool schema definitions.
        
    Returns:
        Ollama ChatResponse object.
    """
    try:
        kwargs = {
            "model": MODEL_NAME,
            "messages": messages,
            "options": {
                "num_predict": 512,
                "temperature": 0.0,
                "num_ctx": 4096,
            },
        }
        if tools:
            kwargs["tools"] = tools
            
        response = ollama.chat(**kwargs)
        return response
    except ollama.ResponseError as e:
        print(f"\n[Ollama Response Error]: {e.error} (Status: {e.status_code})", file=sys.stderr)
        raise
    except Exception as e:
        print(f"\n[LLM Error]: Failed to communicate with Ollama instance: {e}", file=sys.stderr)
        raise
