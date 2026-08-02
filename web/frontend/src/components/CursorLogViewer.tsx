import { Button, Space, Spin, message } from "antd";
import { CopyOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useRef, useState } from "react";

import type { LogWindow } from "../api";

type LogLoader = (params?: { cursor?: string; offset?: number; limit?: number }) => Promise<LogWindow>;

interface CursorLogViewerProps {
  sourceKey: string;
  load: LogLoader;
  active?: boolean;
  pollIntervalMs?: number;
}

interface VisibleWindow {
  text: string;
  start: number;
  end: number;
  total: number;
  chunkSize: number;
}

const EMPTY_WINDOW: VisibleWindow = { text: "", start: 0, end: 0, total: 0, chunkSize: 65536 };

export function CursorLogViewer({
  sourceKey,
  load,
  active = false,
  pollIntervalMs = 1000,
}: CursorLogViewerProps) {
  const [windowState, setWindowState] = useState<VisibleWindow>(EMPTY_WINDOW);
  const [loading, setLoading] = useState(true);
  const [following, setFollowing] = useState(true);
  const stateRef = useRef(windowState);
  const loaderRef = useRef(load);
  const preRef = useRef<HTMLPreElement>(null);
  stateRef.current = windowState;
  loaderRef.current = load;

  useEffect(() => {
    let current = true;
    setLoading(true);
    setFollowing(true);
    loaderRef.current()
      .then((result) => {
        if (!current) return;
        setWindowState({
          text: result.logs,
          start: result.offset,
          end: result.nextOffset,
          total: result.total,
          chunkSize: result.limit,
        });
      })
      .catch((error) => {
        if (current) message.error(error instanceof Error ? error.message : "Logs could not be loaded.");
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => { current = false; };
  }, [sourceKey]);

  const followOnce = useCallback(async () => {
    const current = stateRef.current;
    const result = await loaderRef.current({ cursor: String(current.end), limit: current.chunkSize });
    setWindowState((previous) => {
      if (result.offset < previous.end) {
        return {
          text: result.logs,
          start: result.offset,
          end: result.nextOffset,
          total: result.total,
          chunkSize: result.limit,
        };
      }
      return {
        ...previous,
        text: previous.text + result.logs,
        end: result.nextOffset,
        total: result.total,
        chunkSize: result.limit,
      };
    });
    window.requestAnimationFrame(() => {
      if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight;
    });
  }, []);

  const safeFollow = useCallback(() => {
    void followOnce().catch((error) => {
      setFollowing(false);
      message.error(error instanceof Error ? error.message : "Log following stopped.");
    });
  }, [followOnce]);

  useEffect(() => {
    if (!active || !following) return;
    const timer = window.setInterval(safeFollow, pollIntervalMs);
    return () => window.clearInterval(timer);
  }, [active, following, pollIntervalMs, safeFollow]);

  async function loadEarlier() {
    const current = stateRef.current;
    if (current.start <= 0) return;
    const target = Math.max(0, current.start - current.chunkSize);
    const element = preRef.current;
    const oldHeight = element?.scrollHeight ?? 0;
    const oldTop = element?.scrollTop ?? 0;
    setLoading(true);
    try {
      const result = await loaderRef.current({ offset: target, limit: current.start - target });
      setWindowState((previous) => ({
        ...previous,
        text: result.logs + previous.text,
        start: result.offset,
        total: Math.max(previous.total, result.total),
      }));
      window.requestAnimationFrame(() => {
        if (element) element.scrollTop = oldTop + Math.max(0, element.scrollHeight - oldHeight);
      });
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Earlier logs could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  async function copyLogs() {
    try {
      await navigator.clipboard.writeText(windowState.text);
      message.success("Logs copied");
    } catch {
      message.error("Logs could not be copied.");
    }
  }

  return (
    <Spin spinning={loading}>
      <Space wrap style={{ marginBottom: 8 }}>
        <Button size="small" onClick={() => void loadEarlier()} disabled={windowState.start <= 0}>Earlier</Button>
        {active && (
          <Button size="small" onClick={() => {
            setFollowing((value) => !value);
            if (!following) safeFollow();
          }}>
            {following ? "Stop following" : "Follow"}
          </Button>
        )}
        <Button size="small" icon={<CopyOutlined />} onClick={() => void copyLogs()} disabled={!windowState.text}>Copy logs</Button>
        <span className="muted">{windowState.start}–{windowState.end} / {windowState.total} bytes</span>
      </Space>
      <pre ref={preRef} className="log-view">{windowState.text || "No logs yet."}</pre>
    </Spin>
  );
}
