# ASTRA backend (FastAPI + MongoDB + YOLO11s)

See the repository [README](../README.md) for the complete setup and frontend
connection steps.

Quick start from PowerShell:

```powershell
Set-Location D:\Astra\backend
Copy-Item .env.example .env
# Edit .env with your MongoDB URI and secure JWT/admin credentials.
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The API checks the database and loads the YOLO weights on startup. Visit
`http://localhost:8000/docs` for interactive API documentation.
