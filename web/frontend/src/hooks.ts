import { message } from "antd";
import { useCallback, useEffect, useState } from "react";

export function useAsyncData<T>(loader: () => Promise<T>, initial: T, notifyError = true) {
  const [data, setData] = useState(initial);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const nextData = await loader();
      setData(nextData);
      return nextData;
    } catch (error) {
      const nextError = error as Error;
      setError(nextError);
      if (notifyError) message.error(nextError.message);
      return undefined;
    } finally {
      setLoading(false);
    }
  }, [loader, notifyError]);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data, loading, error, reload, setData };
}
