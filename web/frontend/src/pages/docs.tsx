import { Alert, Card, Empty, Input, Layout, List, Spin, Typography, message } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import { Fragment, useEffect, useMemo, useState } from "react";

import { api } from "../api";
import type { HelpArticle, HelpArticleSummary } from "../api";


function inline(text: string) {
  const parts = text.split(/(`[^`]+`)/g);
  return parts.map((part, index) => part.startsWith("`") && part.endsWith("`") ? <code key={index}>{part.slice(1, -1)}</code> : <Fragment key={index}>{part}</Fragment>);
}


function Markdown({ content }: { content: string }) {
  const lines = content.split("\n");
  const nodes = [];
  let inCode = false;
  let code: string[] = [];
  let bullets: string[] = [];
  const flushBullets = () => {
    if (bullets.length) nodes.push(<ul key={`list-${nodes.length}`}>{bullets.map((value) => <li key={value}>{inline(value)}</li>)}</ul>);
    bullets = [];
  };
  for (const line of lines) {
    if (line.startsWith("```")) {
      if (inCode) { nodes.push(<pre key={`code-${nodes.length}`}><code>{code.join("\n")}</code></pre>); code = []; }
      inCode = !inCode;
      continue;
    }
    if (inCode) { code.push(line); continue; }
    if (line.startsWith("- ")) { bullets.push(line.slice(2)); continue; }
    flushBullets();
    if (line.startsWith("### ")) nodes.push(<Typography.Title level={4} key={`h3-${nodes.length}`}>{line.slice(4)}</Typography.Title>);
    else if (line.startsWith("## ")) nodes.push(<Typography.Title level={3} key={`h2-${nodes.length}`}>{line.slice(3)}</Typography.Title>);
    else if (line.startsWith("# ")) nodes.push(<Typography.Title level={2} key={`h1-${nodes.length}`}>{line.slice(2)}</Typography.Title>);
    else if (/^\|.*\|$/.test(line)) nodes.push(<pre className="docs-table-line" key={`table-${nodes.length}`}>{line}</pre>);
    else if (/^\d+\.\s/.test(line)) nodes.push(<p key={`ordered-${nodes.length}`}>{inline(line)}</p>);
    else if (line.trim()) nodes.push(<Typography.Paragraph key={`p-${nodes.length}`}>{inline(line)}</Typography.Paragraph>);
  }
  flushBullets();
  return <div className="docs-markdown">{nodes}</div>;
}


export function DocsPage() {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<HelpArticleSummary[]>([]);
  const [article, setArticle] = useState<HelpArticle>();
  const [loading, setLoading] = useState(true);

  async function loadList(value = "") {
    setLoading(true);
    try {
      const result = await api.helpArticles(value);
      setItems(result.items);
      if (!article && result.items[0]) setArticle(await api.helpArticle(result.items[0].slug));
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadList(); }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => void loadList(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  const title = useMemo(() => article?.title || "文档中心", [article]);

  return (
    <>
      <div className="toolbar"><h1 className="page-title">文档中心</h1><Input allowClear prefix={<SearchOutlined />} placeholder="搜索配置、策略、操作或错误" value={query} onChange={(event) => setQuery(event.target.value)} style={{ width: 380 }} /></div>
      <Alert type="info" showIcon message="中文操作文档" description="配置键、API字段、LEAN术语和代码保留英文，可通过左侧目录或全文搜索定位。" style={{ marginBottom: 16 }} />
      <Layout style={{ background: "transparent", gap: 16 }}>
        <Layout.Sider width={300} theme="light" style={{ padding: 12, borderRadius: 8, height: "calc(100vh - 190px)", overflow: "auto" }}>
          {loading ? <Spin /> : items.length ? <List dataSource={items} renderItem={(item) => <List.Item style={{ cursor: "pointer", display: "block" }} onClick={async () => setArticle(await api.helpArticle(item.slug))}><strong>{item.title}</strong>{query && <div style={{ color: "#777", fontSize: 12, marginTop: 4 }}>{item.snippet}</div>}</List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        </Layout.Sider>
        <Layout.Content>
          <Card title={title} style={{ minHeight: "calc(100vh - 190px)" }}>{article ? <Markdown content={article.content} /> : <Spin />}</Card>
        </Layout.Content>
      </Layout>
    </>
  );
}
