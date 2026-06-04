import os
import sys
from pathlib import Path

import httpx


DEFAULT_BASE_URL = "https://api-gateway.merge.dev/v1"
DEFAULT_MODEL = "openai/gpt-4o"


def load_dotenv() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_client() -> httpx.Client:
    load_dotenv()
    api_key = os.getenv("MERGE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Set MERGE_API_KEY before running this script, or create a .env file "
            "containing MERGE_API_KEY=your_api_key_here."
        )

    return httpx.Client(
        base_url=os.getenv("MERGE_BASE_URL", DEFAULT_BASE_URL),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=60,
    )


def extract_text(response: dict) -> str:
    parts = []

    for output_item in response.get("output", []):
        content = output_item.get("content")

        if isinstance(content, str):
            parts.append(content)
            continue

        if isinstance(content, list):
            for content_item in content:
                text = content_item.get("text") if isinstance(content_item, dict) else None
                if text:
                    parts.append(text)
                    continue

                thinking = content_item.get("thinking") if isinstance(content_item, dict) else None
                if thinking:
                    parts.append(thinking)
                elif isinstance(content_item, dict) and content_item.get("text"):
                    parts.append(content_item["text"])
            continue

        if content:
            parts.append(str(content))

    return "\n".join(parts).strip()


def send_message(client: httpx.Client, messages: list[dict[str, str]], model: str) -> str:
    response = client.post(
        "/responses",
        json={
            "model": model,
            "input": [
            {
                "type": "message",
                "role": message["role"],
                "content": message["content"],
            }
            for message in messages
            ],
        },
    )
    response.raise_for_status()
    data = response.json()

    text = extract_text(data)
    return text or str(data)


def main() -> int:
    model = os.getenv("MERGE_MODEL", DEFAULT_MODEL)
    client = build_client()

    messages = [
        {
            "role": "system",
            "content": "You are a concise, practical assistant.",
        }
    ]

    if len(sys.argv) > 1:
        messages.append({"role": "user", "content": " ".join(sys.argv[1:])})
        print(send_message(client, messages, model))
        return 0

    print(f"Merge Gateway chat demo using {model}. Type 'exit' to quit.")

    while True:
        user_text = input("\nYou: ").strip()
        if user_text.lower() in {"exit", "quit"}:
            return 0
        if not user_text:
            continue

        messages.append({"role": "user", "content": user_text})
        assistant_text = send_message(client, messages, model)
        messages.append({"role": "assistant", "content": assistant_text})

        print(f"\nAssistant: {assistant_text}")


if __name__ == "__main__":
    raise SystemExit(main())
