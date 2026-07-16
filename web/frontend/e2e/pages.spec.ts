import { expect, Page, test } from "@playwright/test";

function mockState() {
  const settings = {
    defaultAssetClass: "equity",
    defaultMarket: "china",
    defaultVenue: "china",
    defaultResolution: "daily",
    defaultDataType: "trade",
    defaultProvider: "tushare",
    defaultAdjust: "raw",
    defaultStrategyTemplate: "ema_cross",
    defaultCash: 300000,
    defaultStart: "2024-01-01",
    defaultEnd: "2026-07-13",
    chartPointLimit: 10000,
    maxConcurrentJobs: 2,
    jobTimeoutSeconds: 3600,
    logLevel: "INFO",
    dockerImage: "quantconnect/lean:latest",
    researchImage: "quantconnect/research:latest"
  };

  const assetClasses = [
    { key: "equity", name: "Equity", defaultVenue: "usa", defaultResolution: "daily", dataTypes: ["trade"], venues: ["usa", "china", "hkex"], notes: "" },
    { key: "crypto", name: "Crypto", defaultVenue: "binance", defaultResolution: "minute", dataTypes: ["trade"], venues: ["binance"], notes: "" }
  ];
  const markets = [
    { key: "usa", name: "US", currency: "USD", defaultProvider: "yahoo", providers: ["yahoo", "stooq"] },
    { key: "china", name: "China", currency: "CNY", defaultProvider: "tushare", providers: ["tushare", "akshare"] },
    { key: "hongkong", name: "Hong Kong", currency: "HKD", defaultProvider: "stooq", providers: ["stooq"] }
  ];
  const dataProviders = [
    { key: "tushare", name: "TuShare Pro", requiresApiKey: true, supportsBatch: true, markets: ["china"], assetClasses: ["equity"], notes: "" },
    { key: "yahoo", name: "Yahoo", requiresApiKey: false, supportsBatch: false, markets: ["usa"], assetClasses: ["equity"], notes: "" },
    { key: "akshare", name: "Akshare", requiresApiKey: false, supportsBatch: false, markets: ["china"], assetClasses: ["equity"], notes: "" },
    { key: "binance", name: "Binance", requiresApiKey: false, supportsBatch: true, markets: ["usa"], assetClasses: ["crypto"], notes: "" }
  ];

  const templates = [
    { key: "ema_cross", name: "EMA Cross", description: "basic ema", parameters: [{ key: "fast", label: "Fast", type: "number", default: 10 }, { key: "slow", label: "Slow", type: "number", default: 20 }] },
    { key: "momentum", name: "Momentum", description: "sample", parameters: [] }
  ];

  const projects = [
    {
      id: "project-1",
      name: "Momentum QA",
      language: "Python",
      algorithm_class: "MomentumAlgorithm",
      config: { assetClass: "equity", market: "usa", resolution: "daily", dataType: "trade", templateKey: "ema_cross" },
      project_path: "/tmp/project-1",
      main_file: "main.py",
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-06T00:00:00Z"
    }
  ];
  const projectFiles = [{ path: "main.py", name: "main.py", type: "file" } as const];

  const backtests = [{
    id: "run-1",
    status: "success",
    symbol: "AAPL",
    parameters: {
      ticker: "AAPL",
      start: "2024-01-01",
      end: "2024-12-31",
      cash: 100000,
      assetClass: "equity",
      market: "usa",
      venue: "usa",
      resolution: "daily",
      dataType: "trade",
      fast: 12,
      slow: 26
    },
    task_id: "task-1",
    name: "AAPL Momentum",
    project_id: "project-1",
    job_id: "run-1",
    results_dir: "/tmp/run-1",
    result_json_path: "/tmp/run-1/result.json",
    summary_json_path: "/tmp/run-1/summary.json",
    report_html_path: "/tmp/run-1/report.html",
    log_path: "/tmp/run-1/log.txt",
    statistics: { "Net Profit": "12.3", "Sharpe Ratio": "1.2", "End Equity": "112000" },
    validation: { passed: true, severity: "info", gates: [{ name: "price", passed: true, severity: "info" }] },
    experiment: { runId: "run-1", scope: {}, strategy: {}, data: {}, environment: {} },
    fingerprint: { checksum: "abc" },
    created_at: "2026-07-02T00:00:00Z",
    started_at: "2026-07-02T00:02:00Z",
    finished_at: "2026-07-02T00:10:00Z",
    duration_seconds: 480,
    artifacts: ["output.txt"],
  }];

  const charts = {
    statistics: {},
    series: {
      equity: [
        { time: "2024-01-01T00:00:00Z", value: 100000 },
        { time: "2024-01-02T00:00:00Z", value: 101000 }
      ],
      return: [{ time: "2024-01-01T00:00:00Z", value: 1 }],
      drawdown: [{ time: "2024-01-01T00:00:00Z", value: -0.1 }],
      emaFast: [],
      emaSlow: [],
      benchmark: [],
      price: [{ time: "2024-01-01T00:00:00Z", value: 189.5 }]
    },
    orders: [
      {
        time: "2024-01-01T00:00:00Z",
        side: "BUY",
        symbol: "AAPL",
        quantity: 10,
        price: 189.5,
        tag: "entry",
        fill_price: 189.5
      }
    ],
    orderMarkers: [
      {
        time: "2024-01-01T00:00:00Z",
        side: "BUY",
        symbol: "AAPL",
        quantity: 10,
        price: 189.5,
        fillPrice: 189.5,
        equityValue: 100000,
        priceValue: 189.5,
        tag: "entry"
      }
    ]
  };

  const compareResult = {
    items: [
      {
        runId: "run-1",
        name: "AAPL run",
        symbol: "AAPL",
        assetClass: "equity",
        venue: "usa",
        status: "success",
        projectId: "project-1",
        createdAt: "2026-07-02T00:00:00Z",
        finishedAt: "2026-07-02T00:10:00Z",
        parameters: {},
        metrics: {
          totalReturn: 0.12,
          annualReturn: 0.17,
          maxDrawdown: -0.03,
          sharpeRatio: 1.6,
          calmarRatio: 2.2,
          leanSharpeRatio: 1.3,
          totalOrders: 12,
          shortWindowUnstable: false
        },
        equityCurve: [
          { time: "2024-01-01T00:00:00Z", value: 100000 },
          { time: "2024-01-02T00:00:00Z", value: 101000 }
        ],
        drawdownCurve: [{ time: "2024-01-01T00:00:00Z", value: -0.04 }],
        validation: { passed: true, severity: "info", gates: [] },
        experiment: {},
        error: undefined
      }
    ],
    rankings: { returns: ["run-1"] }
  };

  const factorResult = {
    factor: "momentum",
    universe: "ALL_A",
    start_date: "2024-01-01",
    end_date: "2024-12-31",
    forward_days: 1,
    quantiles: 5,
    observations: 120,
    mean_ic: 0.0142,
    mean_rank_ic: 0.0113,
    engine: "python",
    quantile_returns: [
      { quantile: 1, mean_return: -0.004, count: 20 },
      { quantile: 2, mean_return: 0.002, count: 20 }
    ],
    ic_series: [{ trade_date: "2024-01-01", ic: 0.02, count: 15 }],
    rank_ic_series: [{ trade_date: "2024-01-01", rank_ic: 0.014, count: 15 }]
  };

  const evaluationList = [
    {
      id: "eval-1",
      factor_name: "momentum",
      universe_code: "ALL_A",
      created_at: "2026-07-01T00:00:00Z",
      result: factorResult
    }
  ];

  const dependencyHealth = {
    status: "ok",
    dependencies: [
      { service: "database", ok: true, detail: "connected", latency_ms: 12 },
      { service: "redis", ok: true, detail: "connected", latency_ms: 4 }
    ],
    urls: { prometheus: "http://127.0.0.1:9090", grafana: "http://127.0.0.1:3000" }
  };

  const databaseHealth = {
    service: "database",
    ok: true,
    detail: {
      engine: "mysql",
      host: "127.0.0.1",
      port: 3306,
      database: "lean",
      missingTables: [],
      counts: {
        ashare_daily_bars: 1000,
        index_membership_pit: 500
      },
      csi300MembershipRows: 300
    }
  };

  const reports = [{
    id: "report-1",
    source: "system",
    task_id: null,
    run_id: "run-1",
    status: "success",
    result_json_path: "/tmp/run-1/result.json",
    raw_result_object_id: null,
    storedObjects: [{ id: "obj-1", object_key: "report-1.json", sha256: "abc", size: 32 }],
    result: {
      id: "run-1",
      job_id: "run-1",
      summary_metrics: {},
      equity_curve: [],
      drawdown_curve: [],
      orders: [],
      trades: [],
      holdings: [],
      statistics: {},
      performance: null,
      raw_result_path: "/tmp/run-1/result.json",
      created_at: "2026-07-02T00:00:00Z"
    }
  }];

  const objectStore = [{
    key: "models/example.json",
    file_path: "/tmp/object/models/example.json",
    size: 1234,
    updated_at: "2026-07-02T00:00:00Z"
  }];

  const tasks = [{
    id: "task-1",
    kind: "data.fetch",
    status: "succeeded",
    title: "fetch",
    related_id: null,
    parameters: {},
    log_path: "/tmp/task-1.log",
    created_at: "2026-07-02T00:00:00Z",
    started_at: null,
    finished_at: "2026-07-02T00:05:00Z",
    error: null
  }];

  return {
    settings,
    assetClasses,
    markets,
    dataProviders,
    templates,
    projects,
    projectFiles,
    backtests,
    charts,
    compareResult,
    factorResult,
    evaluationList,
    dependencyHealth,
    databaseHealth,
    reports,
    objectStore,
    tasks,
    localDataFetched: false
  };
}

function localDateString() {
  const value = new Date();
  return [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, "0"),
    String(value.getDate()).padStart(2, "0"),
  ].join("-");
}

async function waitForJson(route: any) {
  try {
    return await route.request().json();
  } catch {
    return {};
  }
}

async function setupApiMocks(page: Page) {
  const state = mockState();

  await page.route("**://*/api/**", async (route) => {
    const req = route.request();
    const method = req.method().toUpperCase();
    const url = new URL(req.url());
    const pathname = decodeURIComponent(url.pathname);
    const body = method === "POST" || method === "PUT" ? await waitForJson(route) : {};

    if (method === "GET" && pathname === "/api/health") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "ok", redis: true }) });
    }

    if (method === "GET" && pathname === "/api/health/dependencies") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.dependencyHealth) });
    }

    if (method === "GET" && pathname === "/api/health/database") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.databaseHealth) });
    }

    if (method === "GET" && pathname === "/api/settings") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.settings) });
    }

    if (method === "PUT" && pathname === "/api/settings") {
      Object.assign(state.settings, body);
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.settings) });
    }

    if (method === "GET" && pathname === "/api/asset-classes") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.assetClasses) });
    }

    if (method === "GET" && pathname === "/api/markets") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.markets) });
    }

    if (method === "GET" && pathname === "/api/data-providers") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.dataProviders) });
    }

    if (method === "GET" && pathname === "/api/data/providers") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.dataProviders) });
    }

    if (method === "GET" && pathname === "/api/data-assets") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
    }

    if (method === "GET" && pathname === "/api/data/files") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [], count: 0 }) });
    }

    if (method === "GET" && pathname === "/api/securities/search") {
      const keyword = url.searchParams.get("keyword") || "000001";
      const market = url.searchParams.get("market") || "china";
      const marketLabel = market === "usa" ? "美股" : market === "hongkong" ? "H股" : "A股";
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [{ symbol: keyword.toUpperCase(), market, marketLabel, name: "平安银行", hasLocalData: state.localDataFetched, matchType: "exact", matchField: "code", score: 100 }], count: 1, query: keyword, markets: [market] }) });
    }

    const identifierMatch = pathname.match(/^\/api\/data\/identifiers\/([^/]+)$/);
    if (method === "GET" && identifierMatch) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ symbol: identifierMatch[1], items: [{ provider: "tushare", identifier_type: "ts_code", identifier_value: `${identifierMatch[1]}.SZ`, source: "tushare:stock_basic" }], count: 1 }) });
    }

    if (method === "GET" && pathname === "/api/strategies/templates") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.templates) });
    }

    if (method === "GET" && pathname === "/api/projects") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.projects) });
    }

    const projectFilesMatch = pathname.match(/^\/api\/projects\/([^/]+)\/files$/);
    if (method === "GET" && projectFilesMatch) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.projectFiles) });
    }

    const projectFileMatch = pathname.match(/^\/api\/projects\/([^/]+)\/file$/);
    if (projectFileMatch) {
      if (method === "GET") {
        return route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ path: "main.py", content: "from AlgorithmImports import *\n\nclass TestAlgorithm: pass" })
        });
      }
      if (method === "PUT") {
        return route.fulfill({ contentType: "application/json", body: JSON.stringify({ path: (body as any).path ?? "main.py", size: 100, updated_at: "2026-07-03T00:00:00Z" }) });
      }
    }

    if (method === "POST" && pathname === "/api/projects") {
      const payload = body as any;
      const next = {
        id: `project-${state.projects.length + 1}`,
        name: payload.name ?? "New Project",
        language: "Python",
        algorithm_class: payload.algorithmClass ?? "Algorithm",
        config: {
          assetClass: payload.assetClass ?? "equity",
          market: payload.market ?? "usa",
          resolution: payload.resolution ?? "daily",
          dataType: payload.dataType ?? "trade",
          templateKey: payload.templateKey ?? "ema_cross",
          venue: payload.venue ?? "usa"
        },
        project_path: `/tmp/${payload.name || "project"}`,
        main_file: "main.py",
        created_at: "2026-07-07T00:00:00Z",
        updated_at: "2026-07-07T00:00:00Z",
        parameters: payload.parameters
      };
      state.projects.push(next);
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(next) });
    }

    const projectMatch = pathname.match(/^\/api\/projects\/([^/]+)$/);
    if (projectMatch && method === "PUT") {
      const project = state.projects.find((item: any) => item.id === projectMatch[1]) ?? state.projects[0];
      Object.assign(project, {
        name: (body as any).name ?? project.name,
        config: { ...(project.config ?? {}), ...((body as any).config ?? {}) },
        updated_at: "2026-07-08T00:00:00Z",
      });
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(project) });
    }

    if (/^\/api\/projects\/.+$/.test(pathname) && method === "DELETE") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ deleted: true }) });
    }

    if (method === "GET" && pathname === "/api/symbols") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ symbols: ["AAPL", "MSFT", "000519"], count: 3 }) });
    }

    if (method === "GET" && pathname === "/api/backtests") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.backtests) });
    }

    const runMatch = pathname.match(/^\/api\/backtests\/([^/]+)$/);
    if (method === "GET" && runMatch) {
      const run = state.backtests.find((item: any) => item.id === runMatch[1]);
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(run ?? state.backtests[0]) });
    }

    if (method === "POST" && pathname === "/api/backtests/preflight") {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          ready: true,
          market: (body as any).market,
          assetClass: (body as any).assetClass,
          effectiveSource: (body as any).source || "tushare",
          repaired: [],
          items: [],
        }),
      });
    }

    if (method === "POST" && pathname === "/api/backtests") {
      const payload = body as any;
      const next = {
        id: `run-${state.backtests.length + 1}`,
        status: "queued",
        symbol: payload.symbol,
        parameters: payload,
        task_id: `task-${state.backtests.length + 1}`,
        name: payload.name ?? `${payload.symbol}-run`,
        project_id: payload.projectId,
        job_id: `run-${state.backtests.length + 1}`,
        results_dir: "/tmp/run-new",
        result_json_path: "/tmp/run-new/result.json",
        summary_json_path: "/tmp/run-new/summary.json",
        report_html_path: "/tmp/run-new/report.html",
        log_path: "/tmp/run-new/log.txt",
        statistics: {},
        validation: { passed: true, severity: "ok", gates: [] },
        experiment: {},
        fingerprint: {},
        created_at: "2026-07-08T00:00:00Z"
      };
      state.backtests.push(next);
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(next) });
    }

    const runDetailMatch = pathname.match(/^\/api\/backtests\/([^/]+)\/(chart-data|validation|logs|status|result|cancel)$/);
    if (runDetailMatch) {
      const id = runDetailMatch[1];
      const action = runDetailMatch[2];
      const run = state.backtests.find((item: any) => item.id === id) ?? state.backtests[0];
      if (action === "chart-data") {
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.charts) });
      }
      if (action === "validation") {
        return route.fulfill({ contentType: "application/json", body: { job_id: id, validation: run?.validation ?? null, experiment: run?.experiment ?? null, fingerprint: run?.fingerprint ?? null } });
      }
      if (action === "logs") {
        return route.fulfill({ contentType: "application/json", body: { logs: "line 1\nline 2" } });
      }
      if (action === "result") {
        return route.fulfill({ contentType: "application/json", body: { job: run, result: { id, job_id: id, summary_metrics: { "Recomputed Sharpe": "1.34" }, statistics: run?.statistics ?? {}, orders: [], trades: [], holdings: [], performance: { validation: run?.validation, experiment: run?.experiment }, raw_result_path: "/tmp/result.json" } } });
      }
      if (action === "cancel") {
        return route.fulfill({ contentType: "application/json", body: { ...run, status: "cancelled" } });
      }
    }

    if (method === "POST" && pathname === "/api/compare/backtests") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.compareResult) });
    }

    if (method === "GET" && pathname === "/api/tasks") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(state.tasks) });
    }

    const taskLogMatch = pathname.match(/^\/api\/tasks\/([^/]+)\/logs$/);
    if (method === "GET" && taskLogMatch) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ logs: "task logs" }) });
    }

    const taskDeleteMatch = pathname.match(/^\/api\/tasks\/([^/]+)$/);
    if (method === "DELETE" && taskDeleteMatch) {
      state.tasks = state.tasks.filter((task: any) => task.id !== taskDeleteMatch[1]);
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ deleted: true, id: taskDeleteMatch[1] }) });
    }

    if (method === "GET" && pathname === "/api/optimize") {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
    }

    if (method === "POST" && pathname === "/api/optimize") {
      return route.fulfill({ contentType: "application/json", body: { id: "opt-1", status: "queued", parameters: body, created_at: "2026-07-08T00:00:00Z" } });
    }

    if (method === "GET" && pathname === "/api/factors/engines") {
      return route.fulfill({ contentType: "application/json", body: { available: { python: true, duckdb: true, polars: false }, selected: "python" } });
    }

    if (method === "GET" && pathname === "/api/factors/evaluations") {
      return route.fulfill({ contentType: "application/json", body: { items: state.evaluationList, count: state.evaluationList.length } });
    }

    if (method === "POST" && pathname === "/api/factors/evaluate") {
      const response = { ...state.factorResult, factor: body.factorName ?? "momentum", universe: (body.universeCode ?? "ALL_A"), start_date: "2024-01-01", end_date: "2024-12-31" };
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(response) });
    }

    if (method === "GET" && pathname.startsWith("/api/pit/index-members/")) {
      return route.fulfill({ contentType: "application/json", body: { universe: "CSI300", asOfDate: "2026-07-03", items: [{ universe_code: "CSI300", symbol: "600519", start_date: "2017-01-01", end_date: null, name: "Example", exchange: "SSE" }], count: 1 } });
    }

    if (method === "GET" && pathname.startsWith("/api/cbond/double-low")) {
      return route.fulfill({ contentType: "application/json", body: { asOfDate: "2026-07-03", count: 1, items: [{ bond_code: "123456", bond_name: "Test Bond", stock_symbol: "600519", trade_date: "2026-07-03", close: 105, premium_rate: 0.13, double_low: 120, current_remaining_size: 10 } ] } });
    }

    if (method === "GET" && pathname.startsWith("/api/cbond/call-risk")) {
      return route.fulfill({ contentType: "application/json", body: { asOfDate: "2026-07-03", count: 1, items: [{ bond_code: "123456", bond_name: "Test Bond", announce_date: "2026-06-01", status: "active", last_trade_date: "2026-12-31" }] } });
    }

    if (method === "GET" && pathname.startsWith("/api/futures/agri-main")) {
      return route.fulfill({ contentType: "application/json", body: { asOfDate: "2026-07-03", count: 1, missing: [], items: [{ contract_code: "AG2407", product: "AG", exchange: "SHFE", bar_date: "2026-07-03", close: 10, volume: 1000, open_interest: 100, daysToExpiry: 30 }] } });
    }

    if (method === "GET" && pathname === "/api/research") {
      return route.fulfill({ contentType: "application/json", body: [{ id: "rs-1", status: "running", task_id: "task-2", project_id: "project-1", port: 8888, container_id: "c1", url: "http://127.0.0.1:8888", created_at: "2026-07-05T00:00:00Z" }] });
    }

    if (method === "POST" && pathname === "/api/research") {
      return route.fulfill({ contentType: "application/json", body: { id: "rs-2", status: "running", project_id: (body as any).projectId, port: (body as any).port ?? 8888, created_at: "2026-07-08T00:00:00Z" } });
    }

    const researchStopMatch = pathname.match(/^\/api\/research\/([^/]+)\/stop$/);
    if (method === "POST" && researchStopMatch) {
      return route.fulfill({ contentType: "application/json", body: { id: researchStopMatch[1], status: "stopped", created_at: "2026-07-05T00:00:00Z" } });
    }

    if (method === "GET" && pathname === "/api/paper") {
      return route.fulfill({ contentType: "application/json", body: [] });
    }

    if (method === "POST" && pathname === "/api/paper") {
      return route.fulfill({ contentType: "application/json", body: { id: `paper-${Date.now()}`, status: "running", name: (body as any).name ?? "Paper", project_id: (body as any).projectId, symbol: (body as any).symbol ?? "AAPL", asset_class: (body as any).assetClass ?? "equity", venue: "usa", resolution: "daily", cash: (body as any).cash ?? 100000, equity: 100000, parameters: {}, created_at: "2026-07-08T00:00:00Z", updated_at: "2026-07-08T00:00:00Z" } });
    }

    if (pathname.startsWith("/api/paper/") && pathname.endsWith("/reports")) {
      return route.fulfill({ contentType: "application/json", body: [] });
    }

    const paperStatusMatch = pathname.match(/^\/api\/paper\/([^/]+)\/status$/);
    if (method === "POST" && paperStatusMatch) {
      return route.fulfill({ contentType: "application/json", body: { id: paperStatusMatch[1], status: (body as any).status ?? "paused", name: "Paper", symbol: "AAPL", asset_class: "equity", venue: "usa", resolution: "daily", cash: 100000, equity: 100000, created_at: "2026-07-08T00:00:00Z", updated_at: "2026-07-08T00:00:00Z" } });
    }

    if (method === "GET" && pathname === "/api/reports") {
      return route.fulfill({ contentType: "application/json", body: state.reports });
    }

    if (method === "POST" && pathname === "/api/reports") {
      const next = {
        id: `report-${state.reports.length + 1}`,
        source: "system",
        task_id: null,
        run_id: (body as any).runId,
        status: "queued",
        created_at: "2026-07-08T00:00:00Z"
      };
      state.reports.push(next);
      return route.fulfill({ contentType: "application/json", body: next });
    }

    if (method === "GET" && pathname === "/api/object-store") {
      return route.fulfill({ contentType: "application/json", body: state.objectStore });
    }

    if (pathname.startsWith("/api/object-store/")) {
      if (method === "POST") {
        const key = pathname.replace("/api/object-store/", "");
        const next = { key, file_path: `/tmp/${key}`, size: 64, updated_at: "2026-07-08T00:00:00Z" };
        return route.fulfill({ contentType: "application/json", body: next });
      }
      if (method === "DELETE") {
        return route.fulfill({ contentType: "application/json", body: { deleted: true } });
      }
      if (method === "GET") {
        return route.fulfill({ status: 200, contentType: "text/plain", body: JSON.stringify({}) });
      }
    }

    if (method === "POST" && pathname === "/api/data/fetch-batch") {
      return route.fulfill({ contentType: "application/json", body: { id: "task-fetch", kind: "data.fetch-batch", status: "queued", title: "data.fetch", created_at: "2026-07-08T00:00:00Z", parameters: {}, log_path: "/tmp/task.log" } });
    }

    if (method === "POST" && pathname === "/api/data/fetch") {
      state.localDataFetched = true;
      return route.fulfill({ contentType: "application/json", body: { id: "asset-fetch", symbol: (body as any).symbol, asset_class: (body as any).assetClass, venue: (body as any).venue, resolution: (body as any).resolution, data_type: (body as any).dataType, rows: 2, first_date: (body as any).startDate, last_date: (body as any).endDate, lean_file: "/tmp/asset.zip", created_at: "2026-07-08T00:00:00Z" } });
    }

    if ((method === "GET" || method === "POST") && pathname === "/api/data/query") {
      const items = state.localDataFetched
        ? [
          { timestamp: "2024-01-02", open: 10, high: 11, low: 9.5, close: 10.5, volume: 1000, source: "tushare" },
          { timestamp: "2024-01-03", open: 10.5, high: 12, low: 10, close: 11.5, volume: 1200, source: "tushare" }
        ]
        : [];
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ source: "database", count: items.length, enabled: true, items, message: "ok" }) });
    }

    if (method === "POST" && pathname === "/api/data/import-csv") {
      return route.fulfill({ contentType: "application/json", body: { id: "asset-1", symbol: "AAPL", asset_class: "equity", venue: "usa", resolution: "daily", data_type: "trade", rows: 1, first_date: "2026-07-01", last_date: "2026-07-01", lean_file: "/tmp/asset.zip", created_at: "2026-07-08T00:00:00Z" } });
    }

    if (method === "GET" && pathname === "/api/query-data") {
      return route.fulfill({ contentType: "application/json", body: { source: "mock", count: 0, enabled: true, items: [] } });
    }

    if (method === "GET" && pathname.startsWith("/api/query")) {
      return route.fulfill({ contentType: "application/json", body: { source: "mock", count: 0, enabled: true, items: [] } });
    }

    if (method === "POST" && pathname === "/api/query") {
      return route.fulfill({ contentType: "application/json", body: { source: "mock", count: 0, enabled: true, items: [] } });
    }

    if (method === "GET" && pathname.startsWith("/api/papers")) {
      return route.fulfill({ contentType: "application/json", body: [] });
    }

    if (method === "GET" && pathname === "/api/query-data/candles") {
      return route.fulfill({ contentType: "application/json", body: { source: "mock", count: 0, enabled: true, items: [] } });
    }

    if (method === "GET" && pathname === "/api/query-data/bars") {
      return route.fulfill({ contentType: "application/json", body: { source: "mock", count: 0, enabled: true, items: [] } });
    }

    if (method === "POST" && pathname === "/api/reports/export") {
      return route.fulfill({ contentType: "application/json", body: { url: "/api/reports/download" } });
    }

    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: `Unhandled endpoint: ${method} ${pathname}` }) });
  });
}

async function gotoRoute(page, route: string) {
  const target = route === "/" ? "/#/" : `/#${route}`;
  await page.goto(target);
  await expect(page.getByRole("heading", { level: 1, name: /.+/ })).toBeVisible();
}

async function chooseFirstSelectOption(page: Page) {
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
}

test.describe("Frontend page coverage", () => {
  test.beforeEach(async ({ page }) => {
    await setupApiMocks(page);
  });

  test("Dashboard loads and can enter workspace", async ({ page }) => {
    await gotoRoute(page, "/");
    await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
    await page.getByRole("button", { name: "New Project" }).click();
    await expect(page).toHaveURL(/#\/projects/);
  });

  test("Workspace loads selected project", async ({ page }) => {
    await gotoRoute(page, "/workspace");
    await expect(page.getByRole("heading", { level: 1, name: "Project Workspace" })).toBeVisible();
    await page.getByRole("button", { name: "Refresh" }).click();
  });

  test("Projects list and create flow", async ({ page }) => {
    await gotoRoute(page, "/projects");
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    await page.getByLabel("Name").fill("Smoke Created Project");
    const createReq = page.waitForRequest((req) => req.method() === "POST" && req.url().includes("/api/projects"));
    await page.getByRole("button", { name: "Create" }).click();
    const req = await createReq;
    expect(req.postDataJSON()).toMatchObject({ name: "Smoke Created Project" });
  });

  test("Data page can refresh and fetch batch data", async ({ page }) => {
    await gotoRoute(page, "/data");
    await expect(page.getByRole("heading", { level: 1, name: "Data Library" })).toBeVisible();
    const previewReq = page.waitForRequest((req) => req.url().includes("/api/data/query") && req.method() === "GET");
    const fallbackReq = page.waitForRequest((req) => req.url().includes("/api/data/fetch") && req.method() === "POST");
    await page.getByTestId("market-data-preview-button").click();
    const preview = await previewReq;
    const previewUrl = new URL(preview.url());
    expect(previewUrl.searchParams.get("startDate")).toBe("1990-01-01");
    expect(previewUrl.searchParams.get("endDate")).toBe(localDateString());
    expect(previewUrl.searchParams.get("limit")).toBe("0");
    expect(previewUrl.searchParams.get("providerSource")).toBe("tushare");
    expect(previewUrl.searchParams.get("providerMode")).toBe("strict");
    const fallback = await fallbackReq;
    expect(fallback.postDataJSON()).toMatchObject({
      provider: "tushare",
      outputsize: "full",
      startDate: "1990-01-01",
      endDate: localDateString()
    });
    await expect(page.getByText("Company Info")).toBeVisible();
    const fetchReq = page.waitForRequest((req) => req.url().includes("/api/data/fetch-batch") && req.method() === "POST");
    await page.getByTestId("market-data-fetch-button").click();
    await fetchReq;
  });

  test("Backtests page loads and opens list", async ({ page }) => {
    await gotoRoute(page, "/backtests");
    await expect(page.getByRole("heading", { level: 1, name: "Backtests" })).toBeVisible();
    await page.getByRole("button", { name: "Refresh" }).click();
  });

  test("Optimization compare tab keeps compare button disabled until enough selections", async ({ page }) => {
    await gotoRoute(page, "/optimization");
    await expect(page.getByRole("heading", { level: 1, name: "Optimization" })).toBeVisible();
    await page.getByRole("tab", { name: "Compare Runs" }).click();
    await expect(page.getByRole("button", { name: "Compare" })).toBeDisabled();
  });

  test("Run detail loads charts and logs", async ({ page }) => {
    await gotoRoute(page, "/runs/run-1");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("AAPL Momentum");
    await page.getByRole("button", { name: "Refresh" }).click();
    await expect(page.getByRole("tab", { name: "Charts" })).toBeVisible();
  });

  test("Optimization can be queued", async ({ page }) => {
    await gotoRoute(page, "/optimization");
    await expect(page.getByRole("heading", { level: 1, name: "Optimization" })).toBeVisible();
    await page.getByRole("combobox", { name: /Project/ }).click();
    await chooseFirstSelectOption(page);
    const submitReq = page.waitForRequest((req) => req.method() === "POST" && req.url().includes("/api/optimize"));
    await page.getByRole("button", { name: "Queue Optimization" }).click();
    await submitReq;
  });

  test("Paper page can create and refresh", async ({ page }) => {
    await gotoRoute(page, "/paper");
    await expect(page.getByRole("heading", { level: 1, name: "Paper Replay" })).toBeVisible();
    await page.getByLabel("Name").fill("Smoke Paper");
    await page.getByLabel("Symbol").click();
    await chooseFirstSelectOption(page);
    const createReq = page.waitForRequest((req) => req.method() === "POST" && req.url().includes("/api/paper"));
    await page.getByRole("button", { name: "Create" }).click();
    await createReq;
  });

  test("Research page can start and stop a session", async ({ page }) => {
    await gotoRoute(page, "/research");
    await expect(page.getByRole("heading", { level: 1, name: "Research" })).toBeVisible();
    await page.getByRole("combobox", { name: /Project/ }).click();
    await chooseFirstSelectOption(page);
    const startReq = page.waitForRequest((req) => req.method() === "POST" && req.url().includes("/api/research") && !req.url().includes("/stop"));
    await page.getByRole("button", { name: "Start" }).click();
    await startReq;
  });

  test("Research page evaluates A-share factors", async ({ page }) => {
    await gotoRoute(page, "/research");
    await expect(page.getByRole("heading", { level: 1, name: "Research" })).toBeVisible();
    await page.getByRole("tab", { name: "CSI300 PIT" }).click();
    await page.getByRole("button", { name: "Query" }).click();
    await page.getByRole("tab", { name: "Factors" }).click();
    const evaluateReq = page.waitForRequest((req) => req.method() === "POST" && req.url().includes("/api/factors/evaluate"));
    await page.getByRole("button", { name: "Evaluate" }).click();
    await evaluateReq;
    await expect(page.getByText("Observations").first()).toBeVisible();
  });

  test("Reports page can create report", async ({ page }) => {
    await gotoRoute(page, "/reports");
    await expect(page.getByRole("heading", { level: 1, name: "Reports" })).toBeVisible();
    await page.getByRole("combobox").first().click();
    await chooseFirstSelectOption(page);
    const createReq = page.waitForRequest((req) => req.method() === "POST" && req.url().includes("/api/reports"));
    await page.getByRole("button", { name: "Generate" }).click();
    await createReq;
  });

  test("Object store route is removed from the web shell", async ({ page }) => {
    await page.goto("/#/object-store");
    await expect(page.getByText("Page Not Found")).toBeVisible();
  });

  test("Tasks page can open logs", async ({ page }) => {
    await gotoRoute(page, "/tasks");
    await expect(page.getByRole("heading", { level: 1, name: "Tasks" })).toBeVisible();
    const logsReq = page.waitForRequest((req) => req.method() === "GET" && req.url().includes("/api/tasks/task-1/logs"));
    await page.getByText("Logs", { exact: true }).click();
    await logsReq;
    const deleteReq = page.waitForRequest((req) => req.method() === "DELETE" && req.url().includes("/api/tasks/task-1"));
    await page.getByRole("button", { name: "Delete" }).click();
    await page.getByRole("button", { name: "Delete" }).last().click();
    await deleteReq;
  });

  test("Monitoring page loads", async ({ page }) => {
    await gotoRoute(page, "/monitoring");
    await expect(page.getByRole("heading", { level: 1, name: "Monitoring" })).toBeVisible();
    await page.getByTestId("check-system-status-button").click();
  });

  test("Settings page can save", async ({ page }) => {
    await gotoRoute(page, "/settings");
    await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
    await page.getByLabel("Default Cash").fill("200000");
    const saveReq = page.waitForRequest((req) => req.method() === "PUT" && req.url().includes("/api/settings"));
    await page.getByRole("button", { name: "Save Settings" }).click();
    await saveReq;
  });
});
