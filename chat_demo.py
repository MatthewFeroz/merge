import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

try:
    from rich.columns import Columns
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.text import Text
except ImportError:  # pragma: no cover - friendly nudge if rich isn't installed
    sys.stderr.write(
        "This demo now uses 'rich' for its TUI. Install dependencies first:\n"
        "    pip install -r requirements.txt\n"
    )
    raise


# Windows consoles often default to cp1252, which can't encode emoji. Force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


DEFAULT_BASE_URL = "https://api-gateway.merge.dev/v1"
DEFAULT_MODEL = "openai/gpt-4o"
SYSTEM_PROMPT = "You are a concise, practical assistant."

# Column colors cycle so each model is easy to tell apart at a glance.
PALETTE = ["bright_cyan", "bright_magenta", "bright_green", "bright_yellow", "bright_blue", "bright_red"]

console = Console()


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
        timeout=120,
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


# --------------------------------------------------------------------------- #
# Model discovery (live, from the Merge gateway /models endpoint)
# --------------------------------------------------------------------------- #

def _is_chat_model(model: dict) -> bool:
    """Keep text-in/text-out chat models; drop embeddings, audio, etc."""
    name = model.get("model", "")
    if any(token in name for token in ("embed", "sonic", "vision-7b", "computer-use")):
        return False
    for vendor in (model.get("vendors") or {}).values():
        caps = (vendor or {}).get("capabilities") or {}
        if "text" in (caps.get("output") or []):
            return True
    return False


def fetch_models(client: httpx.Client) -> dict[str, str]:
    """Return {model_id: display_name} for every available chat model."""
    found: dict[str, str] = {}
    # The endpoint paginates; a few generous limits union to the full catalog.
    for params in ({}, {"limit": 1000}, {"page_size": 1000}):
        try:
            data = client.get("/models", params=params).json().get("data", [])
        except Exception:
            continue
        for model in data:
            if model.get("availability_status") != "available":
                continue
            if not _is_chat_model(model):
                continue
            found[model["model"]] = model.get("display_name") or model["model"]
    return found


def roll_models(catalog: dict[str, str], n: int) -> list[str]:
    """Randomly pick n distinct models from the live catalog."""
    pool = list(catalog.keys())
    n = max(1, min(n, len(pool)))
    return random.sample(pool, n)


# --------------------------------------------------------------------------- #
# TUI rendering
# --------------------------------------------------------------------------- #

def banner() -> None:
    console.print()
    console.print(
        Rule("[bold]🎲  MERGE MODEL ARENA  🎲[/]", style="bright_magenta"),
    )
    console.print(
        "[dim]Ask once, hear from several models at once. "
        "Type [bold]/help[/] for commands.[/]\n"
    )


def show_selection(models: list[str], catalog: dict[str, str]) -> None:
    line = Text("🃏 In play: ", style="bold")
    for i, model in enumerate(models):
        color = PALETTE[i % len(PALETTE)]
        line.append(f" #{i + 1} {catalog.get(model, model)} ", style=f"bold {color}")
        line.append(f"({model})  ", style="dim")
    console.print(line)
    console.print()


def render_columns(results: list[tuple[str, str, str]]) -> None:
    """results: list of (model_id, display_name, text)."""
    panels = []
    for i, (model, name, text) in enumerate(results):
        color = PALETTE[i % len(PALETTE)]
        panels.append(
            Panel(
                Text(text or "(no response)"),
                title=f"[bold {color}]#{i + 1} · {name}[/]",
                subtitle=f"[dim]{model}[/]",
                border_style=color,
                padding=(1, 1),
            )
        )
    console.print(Columns(panels, equal=True, expand=True))


def render_copy_blocks(results: list[tuple[str, str, str]]) -> None:
    """Full-width plain blocks under the columns — trivial to select & copy."""
    console.print()
    console.print(Rule("[dim]copy / paste below[/]", style="dim"))
    for i, (model, name, text) in enumerate(results):
        color = PALETTE[i % len(PALETTE)]
        console.print(f"[bold {color}]#{i + 1} · {name}[/] [dim]{model}[/]")
        # Plain print (no markup parsing) keeps the text byte-for-byte copyable.
        console.print("```")
        console.print(text or "(no response)", markup=False, highlight=False)
        console.print("```\n")


def ask_all(client: httpx.Client, histories: dict[str, list], models: list[str]) -> list[tuple[str, str, str]]:
    """Send the latest turn to every selected model concurrently."""

    def one(model: str) -> tuple[str, str]:
        try:
            return model, send_message(client, histories[model], model)
        except httpx.HTTPStatusError as exc:
            return model, f"⚠️  HTTP {exc.response.status_code}: {exc.response.text[:300]}"
        except Exception as exc:  # noqa: BLE001 - surface any error inside its column
            return model, f"⚠️  {type(exc).__name__}: {exc}"

    answers: dict[str, str] = {}
    with console.status("[bold]Consulting the models…[/]", spinner="dots"):
        with ThreadPoolExecutor(max_workers=min(8, len(models))) as pool:
            for model, text in pool.map(one, models):
                answers[model] = text
    return answers


# --------------------------------------------------------------------------- #
# Interactive arena
# --------------------------------------------------------------------------- #

HELP = """[bold]Commands[/]
  [bold]/roll [n][/]   reshuffle to n random models (default 3)
  [bold]/models[/]     list the models currently in play
  [bold]/all[/]        show the full available model catalog
  [bold]/help[/]       show this help
  [bold]exit[/] / [bold]quit[/]  leave the arena

Anything else you type is sent to every model in play, side by side."""


def interactive(client: httpx.Client, default_n: int) -> int:
    catalog = fetch_models(client)
    if not catalog:
        console.print("[red]No models returned by the gateway.[/]")
        return 1

    banner()
    console.print(f"[dim]{len(catalog)} chat models available on the Merge gateway.[/]")

    selected = roll_models(catalog, default_n)
    histories: dict[str, list] = {}

    def reset_histories(models: list[str]) -> None:
        for model in models:
            histories.setdefault(model, [{"role": "system", "content": SYSTEM_PROMPT}])

    reset_histories(selected)
    show_selection(selected, catalog)

    while True:
        try:
            user_text = console.input("[bold bright_white]You ›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye 👋[/]")
            return 0

        if not user_text:
            continue

        lowered = user_text.lower()
        if lowered in {"exit", "quit"}:
            console.print("[dim]bye 👋[/]")
            return 0

        if lowered == "/help":
            console.print(Panel(HELP, border_style="bright_blue"))
            continue

        if lowered == "/models":
            show_selection(selected, catalog)
            continue

        if lowered == "/all":
            names = "\n".join(f"  {m}  [dim]{catalog[m]}[/]" for m in sorted(catalog))
            console.print(Panel(names, title=f"{len(catalog)} available models", border_style="dim"))
            continue

        if lowered.startswith("/roll"):
            parts = user_text.split()
            n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else default_n
            selected = roll_models(catalog, n)
            histories.clear()
            reset_histories(selected)
            console.print("[bold green]🎲 Rerolled![/]")
            show_selection(selected, catalog)
            continue

        # Otherwise: it's a prompt -> fan out to every selected model.
        for model in selected:
            histories[model].append({"role": "user", "content": user_text})

        answers = ask_all(client, histories, selected)

        results = []
        for model in selected:
            text = answers.get(model, "(no response)")
            histories[model].append({"role": "assistant", "content": text})
            results.append((model, catalog.get(model, model), text))

        console.print()
        render_columns(results)
        render_copy_blocks(results)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> int:
    argv = sys.argv[1:]

    # --list-models: dump the catalog and exit.
    if argv and argv[0] in {"--list-models", "--models"}:
        catalog = fetch_models(build_client())
        for model in sorted(catalog):
            console.print(f"{model}  [dim]{catalog[model]}[/]")
        return 0

    # --roll [n] "prompt": one-shot, n random models in columns, then exit.
    if argv and argv[0] == "--roll":
        rest = argv[1:]
        n = 3
        if rest and rest[0].isdigit():
            n = int(rest[0])
            rest = rest[1:]
        prompt = " ".join(rest).strip()
        client = build_client()
        catalog = fetch_models(client)
        selected = roll_models(catalog, n)
        if not prompt:
            return interactive(client, n)  # no prompt -> drop into the arena
        histories = {m: [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}] for m in selected}
        show_selection(selected, catalog)
        answers = ask_all(client, histories, selected)
        results = [(m, catalog.get(m, m), answers.get(m, "")) for m in selected]
        render_columns(results)
        render_copy_blocks(results)
        return 0

    client = build_client()

    # Plain one-shot against a single model (backwards compatible).
    if argv:
        model = os.getenv("MERGE_MODEL", DEFAULT_MODEL)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": " ".join(argv)},
        ]
        console.print(send_message(client, messages, model), markup=False)
        return 0

    # No args -> interactive multi-model arena.
    return interactive(client, default_n=3)


if __name__ == "__main__":
    raise SystemExit(main())
