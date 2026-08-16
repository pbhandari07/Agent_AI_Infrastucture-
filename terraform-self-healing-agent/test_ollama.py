import sys
import ollama

MODEL_NAME = "qwen2.5-coder:1.5b"
PROMPT = "Explain Terraform for_each in simple terms and give one small Azure example."

def main():
    print(f"Connecting to local Ollama API using model '{MODEL_NAME}'...")
    print(f"Sending Prompt: \"{PROMPT}\"\n")
    
    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT,
                }
            ]
        )
        content = response.get("message", {}).get("content", "")
        print("=== Ollama Model Response ===")
        print(content)
        print("=============================")
        print("\nConnection and inference test succeeded!")
    except ollama.ResponseError as e:
        print(f"\n[Ollama Response Error]: {e.error}", file=sys.stderr)
        print(f"Status Code: {e.status_code}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[Error]: Could not connect to local Ollama instance.", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
