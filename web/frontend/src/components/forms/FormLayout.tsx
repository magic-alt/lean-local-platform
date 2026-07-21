import { Collapse } from "antd";
import type { ReactNode } from "react";


function join(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

export function FormGrid({
  children,
  className,
  modal = false,
}: {
  children: ReactNode;
  className?: string;
  modal?: boolean;
}) {
  return <div className={join("form-grid", modal && "form-grid--modal", className)}>{children}</div>;
}

export function FormSection({
  title,
  description,
  children,
  className,
}: {
  title?: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={join("form-section", className)}>
      {(title || description) && (
        <div className="form-section__heading">
          {title && <div className="form-section__title">{title}</div>}
          {description && <div className="form-section__description">{description}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function AdvancedFields({
  children,
  label = "Advanced settings",
  defaultOpen = false,
}: {
  children: ReactNode;
  label?: ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <Collapse
      className="advanced-fields"
      ghost
      defaultActiveKey={defaultOpen ? ["advanced"] : []}
      items={[{ key: "advanced", label, children }]}
    />
  );
}

export function FormActions({ children, align = "end" }: { children: ReactNode; align?: "start" | "end" }) {
  return <div className={join("form-actions", align === "start" && "form-actions--start")}>{children}</div>;
}
