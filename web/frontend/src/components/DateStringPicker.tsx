import { DatePicker, Input, Space } from "antd";
import type { DatePickerProps } from "antd";
import dayjs from "dayjs";

type DateStringPickerProps = Omit<DatePickerProps, "value" | "onChange"> & {
  testId?: string;
  value?: string;
  onChange?: (value: string) => void;
};

export function DateStringPicker({
  testId,
  value,
  onChange,
  style,
  className,
  placeholder,
  disabled,
  allowClear,
  id,
  ...props
}: DateStringPickerProps) {
  function normalizeDate(rawValue: string) {
    const text = rawValue.trim();
    const match = /^([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})$/.exec(text);
    if (!match) {
      return text;
    }
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    if (month < 1 || month > 12 || day < 1) {
      return text;
    }
    const dayOfMonth = new Date(year, month, 0).getDate();
    const normalizedDay = Math.min(day, dayOfMonth);
    return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(normalizedDay).padStart(2, "0")}`;
  }

  const parsed = value ? dayjs(normalizeDate(value), "YYYY-MM-DD", true) : null;

  const normalizedValue = value ? normalizeDate(value) : "";

  return (
    <Space.Compact className={["date-string-picker", className].filter(Boolean).join(" ")} style={{ width: "100%", ...style }}>
      <Input
        id={id}
        data-testid={testId}
        allowClear={allowClear === undefined ? true : Boolean(allowClear)}
        disabled={disabled}
        placeholder={placeholder ?? "YYYY-MM-DD"}
        value={normalizedValue}
        onChange={(event) => onChange?.(normalizeDate(event.target.value))}
      />
      <DatePicker
        {...props}
        allowClear={false}
        disabled={disabled}
        format="YYYY-MM-DD"
        inputReadOnly
        placeholder=""
        style={{ width: 44, flex: "0 0 44px" }}
        value={parsed?.isValid() ? parsed : null}
        onChange={(_, dateString) => onChange?.(Array.isArray(dateString) ? (dateString[0] ?? "") : (dateString ?? ""))}
      />
    </Space.Compact>
  );
}
