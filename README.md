# Safe AI Mailroom (AI Pipe)

## Local setup
1. `python -m venv venv`
2. Windows PowerShell: `.env\Scripts\Activate.ps1`
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and put your AI Pipe token in `AI_API_KEY`.
5. Run: `python app.py`
6. Endpoint: `http://127.0.0.1:5000/v1/mailroom/actions`

## Render
Set the environment variables shown in `render.yaml`. Attach a persistent disk at
`/var/data` before using SQLite for evaluation persistence. Start command:
`uvicorn asgi:application --host 0.0.0.0 --port $PORT --timeout-keep-alive 60`

## Important
This is a starter implementation that demonstrates the contract layers. It needs
end-to-end testing against the assignment grader and further hardening before Save.
In particular, test the provider's JSON mode, the exact receipt signature encoding,
database disk persistence, request limits, and every action-specific dossier pattern.
