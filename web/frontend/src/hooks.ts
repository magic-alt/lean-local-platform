import { message } from "antd";
import { useCallback, useEffect, useState } from "react";

export function useAsyncData<T>(loader: () => Promise<T>, initial: T) {
  const [data, setData] = useState(initial);
  const [loading, setLoading] = useState(false);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await loader());
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setLoading(false);
    }
  }, [loader]);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data, loading, reload, setData };
}
