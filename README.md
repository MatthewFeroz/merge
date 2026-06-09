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

You can also start the server with **no key at all** — visitors then paste their
own Merge API key via the 🔑 button in the header. The key is kept in the
browser's localStorage and sent with each request; the server never stores it.
This is the mode to use for a public deployment, so strangers can't spend your
credits.

### Deploy to the internet

The repo ships with a `Dockerfile` and a `render.yaml`, so any of these work:

**Render (easiest, free tier):**

1. Push this repo to GitHub.
2. On [render.com](https://render.com) choose **New → Blueprint** and point it
   at the repo — `render.yaml` configures everything, including a health check.
3. Don't set `MERGE_API_KEY` for a public instance (visitors bring their own
   key). Set it as a secret env var only for a private/team deployment.

**Railway / Fly.io / anything that runs Docker:**

```bash
docker build -t merge-arena .
docker run -p 8000:8000 merge-arena
```

The server reads `PORT` (standard on these platforms) and binds `0.0.0.0`
automatically when it's set.

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
