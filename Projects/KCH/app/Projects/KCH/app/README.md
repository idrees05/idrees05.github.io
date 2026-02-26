# KCH UAT Test Runner

Role-based UAT test runner for the KCH Copilot project.

## Quick start (local)

```bash
cd Projects/KCH/app
pip install -r requirements.txt
cp .env.example .env        # edit ACCESS_CODE and SECRET_KEY
uvicorn main:app --reload
```

Open http://localhost:8000 and sign in with your access code.

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy URL | `sqlite:///./uat.db` |
| `ACCESS_CODE` | Tester access code | `changeme` |
| `ADMIN_CODE` | Admin access code | `adminchangeme` |
| `SECRET_KEY` | Cookie signing key | dev value |
| `UPLOAD_DIR` | Evidence upload directory | `./uploads` |
| `CSV_DIR` | Path to CSV files | `../` |

## CSV files expected (in `CSV_DIR`)

- `KCH_Copilot_UAT_Test_Scripts_Final - Everyday Users.csv`
- `KCH_Copilot_UAT_Test_Scripts_Final - Power Users.csv`
- `KCH_Copilot_UAT_Test_Scripts_Final - Specialist Users.csv`
- `KCH_Copilot_UAT_Test_Scripts_Final - Master Index.csv`

Scripts are imported automatically on startup. Use `/admin` → Re-import CSVs to refresh.

## Deploy to Render

1. Push to GitHub
2. Create a new Web Service on Render pointing to this repo
3. Set root directory to `Projects/KCH/app`
4. Render will use `render.yaml` to provision a free Postgres database
5. Set `ACCESS_CODE`, `ADMIN_CODE`, and `SECRET_KEY` env vars in the dashboard

> **Note:** File uploads are ephemeral on Render free tier. Use URL-based evidence for production.
