# Merge
## Merge Gateway Chat Demo

Install the SDK:

```powershell
pip install -r requirements.txt
```

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
