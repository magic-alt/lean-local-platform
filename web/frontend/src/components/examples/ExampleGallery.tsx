import { Button, Card, Empty, Input, Space, Tag, message } from "antd";
import { CopyOutlined, SearchOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";

import { api } from "../../api";
import type { Project, WorkflowExample } from "../../api";


export function ExampleGallery({ kind, onCreated }: { kind: WorkflowExample["kind"]; onCreated?: (project: Project, example: WorkflowExample) => void }) {
  const [items, setItems] = useState<WorkflowExample[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<string>();

  useEffect(() => {
    void api.examples(kind).then((result) => setItems(result.items)).catch((error) => message.error((error as Error).message));
  }, [kind]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return !needle ? items : items.filter((item) => `${item.name} ${item.description} ${item.tags.join(" ")}`.toLowerCase().includes(needle));
  }, [items, query]);

  async function instantiate(example: WorkflowExample) {
    setBusy(example.key);
    try {
      const result = await api.instantiateExample(kind, example.key);
      message.success(`已创建可编辑项目：${result.project.display_name || result.project.name}`);
      window.dispatchEvent(new CustomEvent("lean-example-instantiated", { detail: result }));
      onCreated?.(result.project, example);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(undefined);
    }
  }

  return (
    <Card title="可直接使用的案例" extra={<Input allowClear prefix={<SearchOutlined />} placeholder="搜索案例" value={query} onChange={(event) => setQuery(event.target.value)} style={{ width: 240 }} />}>
      {!filtered.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
        <div className="grid">
          {filtered.map((item) => (
            <Card key={item.key} size="small" title={item.name} extra={<Tag>{item.mode}</Tag>}>
              <p style={{ minHeight: 44 }}>{item.description}</p>
              <Space wrap style={{ marginBottom: 12 }}>{item.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space>
              <div><Button type="primary" icon={<CopyOutlined />} loading={busy === item.key} onClick={() => instantiate(item)}>使用案例</Button></div>
            </Card>
          ))}
        </div>
      )}
    </Card>
  );
}
