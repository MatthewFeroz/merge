# Merge
## Merge Gateway Chat Demo

Install the SDK:

```powershell
pip install -r requirements.txt
```

### Web UI — model arena

A dark, terminal-style chat page. Roll a handful of models, send one prompt,
and compare each model's answer side by side — every output box has a copy
button in its top-right corner. Great for drafting LinkedIn hooks.

```powershell
$env:MERGE_API_KEY="your_api_key_here"   # or a .env file (see below)
python .\server.py                        # -> http://127.0.0.1:8000
```

The key stays server-side; the browser only talks to the local server.

### CLI

Set your API key:

```powershell
$env:MERGE_API_KEY="your_api_key_here"
```

Or create a `.env` file in this folder:

```text
MERGE_API_KEY=your_api_key_here
```

Run a one-shot prompt:

```powershell
python .\chat_demo.py "Explain recursion with one Python example."
```

Or start an interactive chat:

```powershell
python .\chat_demo.py
```

Optional model override:

```powershell
$env:MERGE_MODEL="anthropic/claude-sonnet-4-20250514"
python .\chat_demo.py
```
