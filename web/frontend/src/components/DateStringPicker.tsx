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
  const parsed = value ? dayjs(value) : null;
  return (
    <Space.Compact className={["date-string-picker", className].filter(Boolean).join(" ")} style={{ width: "100%", ...style }}>
      <Input
        id={id}
        data-testid={testId}
        allowClear={allowClear === undefined ? true : Boolean(allowClear)}
        disabled={disabled}
        placeholder={placeholder ?? "YYYY-MM-DD"}
        value={value ?? ""}
        onChange={(event) => onChange?.(event.target.value)}
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
