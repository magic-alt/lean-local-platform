import { DatePicker } from "antd";
import type { DatePickerProps } from "antd";
import dayjs from "dayjs";

type DateStringPickerProps = Omit<DatePickerProps, "value" | "onChange"> & {
  testId?: string;
  value?: string;
  onChange?: (value: string) => void;
};

export function DateStringPicker({ testId, value, onChange, style, ...props }: DateStringPickerProps) {
  const parsed = value ? dayjs(value) : null;
  return (
    <DatePicker
      {...props}
      allowClear={props.allowClear ?? true}
      format="YYYY-MM-DD"
      inputReadOnly={false}
      placeholder={props.placeholder ?? "YYYY-MM-DD"}
      style={{ width: "100%", ...style }}
      data-testid={testId}
      value={parsed?.isValid() ? parsed : null}
      onChange={(_, dateString) => onChange?.(Array.isArray(dateString) ? (dateString[0] ?? "") : (dateString ?? ""))}
    />
  );
}
