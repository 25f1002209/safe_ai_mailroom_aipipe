# Safe AI Mailroom — AI Pipe + Render Free + Neon PostgreSQL

## Free deployment architecture
- Render Free Web Service hosts the API.
- Neon Free PostgreSQL stores evaluations, proposals, cache entries, and receipts.
- AI Pipe is used for dossier interpretation.

## Local setup
1. Create a Neon PostgreSQL database and copy its connection string.
2. Create `.env` from `.env.example`.
3. Set `AI_API_KEY` and `DATABASE_URL`.
4. Create a virtual environment and install `requirements.txt`.
5. Run `python app.py` locally or `uvicorn asgi:application --port 5000`.

## Render
Create a Web Service from your GitHub repository.
Build command: `pip install -r requirements.txt`
Start command: `uvicorn asgi:application --host 0.0.0.0 --port $PORT --timeout-keep-alive 60`
Choose the Free instance. Set `AI_API_KEY`, `DATABASE_URL`, `AI_BASE_URL`, `AI_MODEL`, `AI_TIMEOUT`, and `MAX_REQUEST_BYTES`.
No Render disk is required because application state is stored in Neon.

## Important limitations
Render Free services spin down after 15 minutes idle and can take about a minute to wake.
This can exceed the assignment's 55-second request deadline on a cold start. Free services also have ephemeral local files; do not store state locally.
Neon Free has usage quotas and can scale compute to zero.

This package is a PostgreSQL-adapted starter, not a verified full-marks submission.
It still needs end-to-end contract testing, strict atomic validation, robust batch inference,
action authorization coverage, and exact grader receipt-signature testing before using a graded Check.
