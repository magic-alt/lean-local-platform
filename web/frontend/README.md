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
- Docs
- Settings

Main workflow:

1. Open `Workspace`.
2. Create or select a project, or instantiate a backtest/optimization/research example.
3. Use `Data` for first full/then incremental one-click data, explicit on-demand downloads, CSV templates and dataset previews.
4. Run one job or create an experiment batch across symbols, strategies, parameters, rolling windows or a PIT universe.
5. Inspect child progress, metrics, charts, order markers, artifacts and structured reports; cancel or retry failed batch items when needed.
6. Use `Docs` to search configuration, strategy and troubleshooting guidance.
