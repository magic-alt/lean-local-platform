# Frontend

The frontend is a React/Vite app for the local LEAN workbench. It uses Ant Design for the workbench UI, ECharts for backtest charts, and Monaco Editor for project code editing.

Run in development:

```bash
cd /Users/kaermax/lean-platform/web/frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`.

For stable environment behavior, use the default pair:
- Backend API: `127.0.0.1:8000`
- Frontend UI: `127.0.0.1:5173`

Frontend runs with strict port binding (`--port 5173 --strictPort`) and will fail fast if 5173 is already occupied instead of falling back to 5174/5175.

For consistency, keep the backend on `127.0.0.1:8000` while running the frontend.

Build static assets for FastAPI to serve:

```bash
npm run build
```

Pages:

- Dashboard
- Workspace
- Projects
- Data
- Backtests
- Optimization
- Research
- Reports
- Object Store
- Tasks and logs
- Settings

Main workflow:

1. Open `Workspace`.
2. Create or select a project and choose a strategy template.
3. Use the `Data` tab to download US, A-share, or Hong Kong symbols into local LEAN data.
4. Use the `Backtest` tab to run Docker LEAN against the selected project, market, symbol, and strategy parameters.
5. Open `Results` to inspect metrics, charts, order markers, artifacts, and reports.
