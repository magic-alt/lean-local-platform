import {
  Alert,
  Button,
  Card,
  Drawer,
  Empty,
  Input,
  Layout,
  Space,
  Spin,
  Tag,
  Typography,
  message
} from "antd";
import {
  CopyOutlined,
  DownOutlined,
  MenuOutlined,
  RightOutlined,
  SearchOutlined
} from "@ant-design/icons";
import GithubSlugger from "github-slugger";
import {
  Children,
  cloneElement,
  isValidElement,
  type ComponentPropsWithoutRef,
  type ReactElement,
  type ReactNode,
  useEffect,
  useMemo,
  useState
} from "react";
import ReactMarkdown, { type Components, type ExtraProps } from "react-markdown";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";

import { api } from "../api";
import type { HelpArticle, HelpArticleSummary } from "../api";


const CATEGORY_LABELS: Record<string, string> = {
  "getting-started": "入门",
  experiments: "策略与实验",
  data: "数据",
  operations: "运行与维护",
  api: "接口",
  platform: "平台设计",
  development: "开发参考",
  history: "历史记录"
};

type Heading = { level: number; text: string; id: string };


function headingText(value: string) {
  return value
    .replace(/!\[([^]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^]]+)\]\([^)]+\)/g, "$1")
    .replace(/[`*_~]/g, "")
    .trim();
}


function extractHeadings(content: string): Heading[] {
  const slugger = new GithubSlugger();
  const headings: Heading[] = [];
  let inCode = false;
  for (const line of content.split("\n")) {
    if (line.trim().startsWith("```")) {
      inCode = !inCode;
      continue;
    }
    if (inCode) continue;
    const match = /^(#{1,4})\s+(.+?)\s*$/.exec(line);
    if (!match) continue;
    const text = headingText(match[2]);
    const id = slugger.slug(text);
    if (match[1].length >= 2) headings.push({ level: match[1].length, text, id });
  }
  return headings;
}


function docSlugFromMarkdown(href: string) {
  const withoutFragment = href.split("#", 1)[0];
  const parts = withoutFragment.split("/").filter(Boolean);
  const filename = parts.at(-1) || "";
  if (filename.toLowerCase() === "readme.md" && parts.includes("history")) return "history";
  const stem = filename.replace(/\.md$/i, "").replaceAll("_", "-");
  return parts.includes("history") ? `history-${stem}` : stem;
}


function internalDocumentTarget(href: string, currentSlug: string) {
  if (href.startsWith("#")) {
    return { pathname: `/docs/${currentSlug}`, search: `?section=${encodeURIComponent(href.slice(1))}` };
  }
  const [path, fragment] = href.split("#", 2);
  if (!/\.md$/i.test(path)) return undefined;
  const slug = docSlugFromMarkdown(path);
  return { pathname: `/docs/${slug}`, search: fragment ? `?section=${encodeURIComponent(fragment)}` : "" };
}


function copyText(value: string) {
  void navigator.clipboard.writeText(value).then(
    () => message.success("链接已复制"),
    () => message.error("浏览器未允许复制")
  );
}


function HeadingElement({
  level,
  children,
  id,
  ...props
}: ComponentPropsWithoutRef<"h2"> & ExtraProps & { level: 2 | 3 | 4 }) {
  const TagName = `h${level}` as "h2" | "h3" | "h4";
  const copyUrl = () => {
    const params = new URLSearchParams(window.location.hash.split("?", 2)[1] || "");
    params.set("section", String(id || ""));
    const path = window.location.hash.split("?", 1)[0];
    copyText(`${window.location.origin}/${path}?${params.toString()}`);
  };
  return (
    <TagName id={id} {...props} className={`docs-heading docs-heading-${level}`}>
      <span>{children}</span>
      {id && <button type="button" className="docs-heading-copy" onClick={copyUrl} aria-label="复制章节链接"><CopyOutlined /></button>}
    </TagName>
  );
}


function MarkdownPre({ children }: { children?: ReactNode }) {
  const child = Children.only(children) as ReactElement<{ children?: ReactNode; className?: string }>;
  const content = isValidElement(child) ? String(child.props.children ?? "").replace(/\n$/, "") : "";
  const language = isValidElement(child) ? child.props.className?.replace("language-", "") : undefined;
  return (
    <div className="docs-code-block">
      <div className="docs-code-toolbar">
        <span>{language || "text"}</span>
        <Button type="text" size="small" icon={<CopyOutlined />} onClick={() => void navigator.clipboard.writeText(content)}>复制</Button>
      </div>
      <pre>{isValidElement(child) ? cloneElement(child) : child}</pre>
    </div>
  );
}


function MarkdownArticle({ article }: { article: HelpArticle }) {
  const components = useMemo<Components>(() => ({
    h2: (props) => <HeadingElement level={2} {...props} />,
    h3: (props) => <HeadingElement level={3} {...props} />,
    h4: (props) => <HeadingElement level={4} {...props} />,
    pre: MarkdownPre,
    table: ({ children, ...props }) => <div className="docs-table-scroll"><table {...props}>{children}</table></div>,
    a: ({ href = "", children, ...props }) => {
      const target = internalDocumentTarget(href, article.slug);
      if (target) return <Link to={target}>{children}</Link>;
      if (/^https?:\/\//i.test(href)) return <a href={href} target="_blank" rel="noreferrer" {...props}>{children}</a>;
      return <a href={href} {...props}>{children}</a>;
    },
    img: ({ src = "", alt = "", ...props }) => {
      const target = /^https?:\/\//i.test(src)
        ? src
        : `/api/help/assets/${src.replace(/^\.\//, "").replace(/^assets\//, "")}`;
      return <img src={target} alt={alt} loading="lazy" {...props} />;
    }
  }), [article.slug]);
  return (
    <div className="docs-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSlug]} components={components} skipHtml>
        {article.content}
      </ReactMarkdown>
    </div>
  );
}


function NavigationItems({
  items,
  query,
  activeSlug,
  onSelect
}: {
  items: HelpArticleSummary[];
  query: string;
  activeSlug?: string;
  onSelect: (slug: string) => void;
}) {
  const [collapsed, setCollapsed] = useState<Record<"guide" | "reference", boolean>>({ guide: false, reference: false });
  if (!items.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的文档" />;
  if (query.trim()) {
    return <div className="docs-search-results">{items.map((item) => (
      <button key={item.slug} type="button" className={`docs-nav-item ${item.slug === activeSlug ? "active" : ""}`} onClick={() => onSelect(item.slug)}>
        <strong>{item.title}</strong>
        <span>{item.snippet}</span>
      </button>
    ))}</div>;
  }
  const groups = ["guide", "reference"] as const;
  return <>{groups.map((group) => {
    const groupItems = items.filter((item) => item.group === group);
    const categories = [...new Set(groupItems.map((item) => item.category))];
    const isCollapsed = collapsed[group];
    return (
      <section className="docs-nav-group" key={group}>
        <button
          type="button"
          className="docs-nav-group-toggle"
          aria-expanded={!isCollapsed}
          onClick={() => setCollapsed((value) => ({ ...value, [group]: !value[group] }))}
        >
          <span>{group === "guide" ? "操作教程" : "技术参考"}</span>
          {isCollapsed ? <RightOutlined /> : <DownOutlined />}
        </button>
        {!isCollapsed && categories.map((category) => (
          <div key={category} className="docs-nav-category">
            <h3>{CATEGORY_LABELS[category] || category}</h3>
            {groupItems.filter((item) => item.category === category).map((item) => (
              <button key={item.slug} type="button" className={`docs-nav-item ${item.slug === activeSlug ? "active" : ""}`} onClick={() => onSelect(item.slug)}>
                <span>{item.title}</span>
                {item.status === "historical" && <Tag color="default">历史</Tag>}
              </button>
            ))}
          </div>
        ))}
      </section>
    );
  })}</>;
}


export function DocsPage() {
  const { slug = "index" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [items, setItems] = useState<HelpArticleSummary[]>([]);
  const [article, setArticle] = useState<HelpArticle>();
  const [listLoading, setListLoading] = useState(true);
  const [articleLoading, setArticleLoading] = useState(true);
  const [articleError, setArticleError] = useState<string>();
  const [navigationOpen, setNavigationOpen] = useState(false);

  const headings = useMemo(() => extractHeadings(article?.content || ""), [article?.content]);
  const currentIndex = items.findIndex((item) => item.slug === slug);
  const previous = currentIndex > 0 ? items[currentIndex - 1] : undefined;
  const next = currentIndex >= 0 && currentIndex < items.length - 1 ? items[currentIndex + 1] : undefined;

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setListLoading(true);
      void api.helpArticles(query).then(
        (result) => setItems(result.items),
        (error: Error) => message.error(error.message)
      ).finally(() => setListLoading(false));
      const params = new URLSearchParams(searchParams);
      if (query.trim()) params.set("q", query.trim()); else params.delete("q");
      setSearchParams(params, { replace: true });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    setArticleLoading(true);
    setArticleError(undefined);
    void api.helpArticle(slug).then(
      (value) => setArticle(value),
      (error: Error) => { setArticle(undefined); setArticleError(error.message); }
    ).finally(() => setArticleLoading(false));
  }, [slug]);

  useEffect(() => {
    const section = searchParams.get("section");
    if (!article || !section) return;
    const timer = window.setTimeout(() => document.getElementById(section)?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    return () => window.clearTimeout(timer);
  }, [article, location.search]);

  const openArticle = (nextSlug: string) => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    navigate({ pathname: `/docs/${nextSlug}`, search: params.toString() ? `?${params}` : "" });
    setNavigationOpen(false);
  };

  const navigation = listLoading
    ? <div className="docs-loading"><Spin /></div>
    : <NavigationItems items={items} query={query} activeSlug={slug} onSelect={openArticle} />;
  const toc = headings.length ? (
    <nav className="docs-toc" aria-label="页内目录">
      <h2>本页目录</h2>
      {headings.map((heading) => {
        const params = new URLSearchParams(searchParams);
        params.set("section", heading.id);
        return <Link key={heading.id} className={`docs-toc-level-${heading.level}`} to={{ pathname: `/docs/${slug}`, search: `?${params}` }} onClick={() => setNavigationOpen(false)}>{heading.text}</Link>;
      })}
    </nav>
  ) : <Typography.Text type="secondary">本文没有二级目录</Typography.Text>;

  return (
    <div className="docs-page">
      <div className="toolbar docs-toolbar">
        <Space>
          <Button className="docs-mobile-button" icon={<MenuOutlined />} onClick={() => setNavigationOpen(true)} aria-label="打开文档目录" />
          <h1 className="page-title">文档中心</h1>
        </Space>
        <Input allowClear prefix={<SearchOutlined />} placeholder="搜索配置、API、操作或错误" value={query} onChange={(event) => setQuery(event.target.value)} />
      </div>
      <Layout className="docs-layout">
        <Layout.Sider width={300} theme="light" className="docs-sidebar">
          {navigation}
          <div className="docs-sidebar-toc">{toc}</div>
        </Layout.Sider>
        <Layout.Content className="docs-content">
          <Card>
            {articleLoading && <div className="docs-loading"><Spin /></div>}
            {articleError && <Alert type="error" showIcon message="文档加载失败" description={articleError} />}
            {article && !articleLoading && (
              <>
                <div className="docs-article-meta">
                  <Space wrap>
                    <Tag color={article.group === "guide" ? "blue" : "purple"}>{article.group === "guide" ? "操作教程" : "技术参考"}</Tag>
                    <Tag>{CATEGORY_LABELS[article.category] || article.category}</Tag>
                    {article.status === "historical" && <Tag color="default">历史快照</Tag>}
                  </Space>
                  {article.summary && <Typography.Paragraph type="secondary">{article.summary}</Typography.Paragraph>}
                </div>
                {article.status === "historical" && <Alert type="warning" showIcon message="这是历史问题与证据快照，不代表当前代码状态。" style={{ marginBottom: 18 }} />}
                <MarkdownArticle article={article} />
                <div className="docs-pagination">
                  {previous ? <Button onClick={() => openArticle(previous.slug)}>← {previous.title}</Button> : <span />}
                  {next ? <Button onClick={() => openArticle(next.slug)}>{next.title} →</Button> : <span />}
                </div>
              </>
            )}
          </Card>
        </Layout.Content>
      </Layout>
      <Drawer title="文档与本页目录" placement="left" open={navigationOpen} onClose={() => setNavigationOpen(false)}>{navigation}<div className="docs-sidebar-toc">{toc}</div></Drawer>
    </div>
  );
}
