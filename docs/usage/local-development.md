# Local Development

From the repository root:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements\dev.txt
Copy-Item backend\.env.example backend\.env
.\backend\.venv\Scripts\python.exe -m uvicorn api.main:app --app-dir backend\src --host 127.0.0.1 --port 8000 --reload
```

In a second terminal:

```powershell
cd frontend
npm install
npm start
```

The Angular development server proxies `/api` requests to
`http://127.0.0.1:8000`, so the frontend and backend use the same relative API
contract in development and deployment.
