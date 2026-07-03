# Frontend

The frontend is a React/Vite app for the local LEAN workbench. It uses Ant Design for the workbench UI, ECharts for backtest charts, and Monaco Editor for project code editing.

Run in development:

```bash
cd /Users/kaermax/Lean/docker-demo/web/frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`.

Use another backend port:

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev
```

Build static assets for FastAPI to serve:

```bash
npm run build
```

Pages:

- Dashboard
- LEAN capabilities
- Workspace
- Projects
- Data
- Backtests
- Optimization
- Research
- Reports
- Object Store
- Tasks and logs

Main workflow:

1. Open `Workspace`.
2. Create or select the DJIA EMA project.
3. Use the `Data` tab to download current Dow Jones Industrial Average components into local LEAN data.
4. Use the `Backtest` tab to run Docker LEAN against the selected project and symbol.
5. Open `Results` to inspect metrics, charts, order markers, artifacts, and reports.
