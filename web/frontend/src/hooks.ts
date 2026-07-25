import { message } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";

type AsyncLoader<T> = () => Promise<T>;

interface AsyncCacheEntry<T> {
  data: T | undefined;
  error: Error | null;
  hasData: boolean;
  loading: boolean;
  promise: Promise<T | undefined> | null;
  updatedAt: number;
  listeners: Set<() => void>;
}

const CACHE_FRESH_MS = 15_000;
const MAX_KEYED_CACHE_ENTRIES = 100;
const asyncDataCache = new WeakMap<AsyncLoader<unknown>, AsyncCacheEntry<unknown>>();
const keyedAsyncDataCache = new Map<string, AsyncCacheEntry<unknown>>();

function cacheEntry<T>(loader: AsyncLoader<T>, cacheKey?: string): AsyncCacheEntry<T> {
  if (cacheKey) {
    const keyed = keyedAsyncDataCache.get(cacheKey) as AsyncCacheEntry<T> | undefined;
    if (keyed) {
      keyedAsyncDataCache.delete(cacheKey);
      keyedAsyncDataCache.set(cacheKey, keyed as AsyncCacheEntry<unknown>);
      return keyed;
    }
    if (keyedAsyncDataCache.size >= MAX_KEYED_CACHE_ENTRIES) {
      const evictable = [...keyedAsyncDataCache.entries()].find(([, entry]) => entry.listeners.size === 0);
      if (evictable) keyedAsyncDataCache.delete(evictable[0]);
    }
    const entry: AsyncCacheEntry<T> = {
      data: undefined,
      error: null,
      hasData: false,
      loading: false,
      promise: null,
      updatedAt: 0,
      listeners: new Set()
    };
    keyedAsyncDataCache.set(cacheKey, entry as AsyncCacheEntry<unknown>);
    return entry;
  }
  const cached = asyncDataCache.get(loader as AsyncLoader<unknown>) as AsyncCacheEntry<T> | undefined;
  if (cached) return cached;
  const entry: AsyncCacheEntry<T> = {
    data: undefined,
    error: null,
    hasData: false,
    loading: false,
    promise: null,
    updatedAt: 0,
    listeners: new Set()
  };
  asyncDataCache.set(loader as AsyncLoader<unknown>, entry as AsyncCacheEntry<unknown>);
  return entry;
}

function publish(entry: AsyncCacheEntry<unknown>) {
  entry.listeners.forEach((listener) => listener());
}

function loadEntry<T>(loader: AsyncLoader<T>, notifyError: boolean, force = false, cacheKey?: string) {
  const entry = cacheEntry(loader, cacheKey);
  if (entry.promise) return entry.promise;
  if (!force && entry.hasData && Date.now() - entry.updatedAt < CACHE_FRESH_MS) {
    return Promise.resolve(entry.data);
  }

  entry.loading = true;
  entry.error = null;
  publish(entry as AsyncCacheEntry<unknown>);
  entry.promise = loader()
    .then((nextData) => {
      entry.data = nextData;
      entry.hasData = true;
      entry.updatedAt = Date.now();
      return nextData;
    })
    .catch((error: unknown) => {
      const nextError = error instanceof Error ? error : new Error(String(error));
      entry.error = nextError;
      if (notifyError) message.error(nextError.message);
      return undefined;
    })
    .finally(() => {
      entry.loading = false;
      entry.promise = null;
      publish(entry as AsyncCacheEntry<unknown>);
    });
  return entry.promise;
}

export function useAsyncData<T>(loader: AsyncLoader<T>, initial: T, notifyError = true, cacheKey?: string) {
  const loaderRef = useRef(loader);
  const initialRef = useRef(initial);
  const cacheKeyRef = useRef(cacheKey);
  loaderRef.current = loader;
  initialRef.current = initial;
  cacheKeyRef.current = cacheKey;

  const initialEntry = cacheEntry(loader, cacheKey);
  const [data, setLocalData] = useState<T>(() => initialEntry.hasData ? initialEntry.data as T : initial);
  const [loading, setLoading] = useState(initialEntry.loading);
  const [error, setError] = useState<Error | null>(initialEntry.error);

  const reload = useCallback(
    () => loadEntry(loaderRef.current, notifyError, true, cacheKeyRef.current),
    [notifyError]
  );

  const setData = useCallback((value: T | ((previous: T) => T)) => {
    const entry = cacheEntry(loaderRef.current, cacheKeyRef.current);
    const previous = entry.hasData ? entry.data as T : initialRef.current;
    entry.data = typeof value === "function"
      ? (value as (previous: T) => T)(previous)
      : value;
    entry.hasData = true;
    entry.error = null;
    entry.updatedAt = Date.now();
    publish(entry as AsyncCacheEntry<unknown>);
  }, []);

  useEffect(() => {
    const entry = cacheEntry(loader, cacheKey);
    const sync = () => {
      if (entry.hasData) setLocalData(entry.data as T);
      setLoading(entry.loading);
      setError(entry.error);
    };
    entry.listeners.add(sync);
    sync();
    void loadEntry(loader, notifyError, false, cacheKey);
    return () => {
      entry.listeners.delete(sync);
    };
  }, [cacheKey, loader, notifyError]);

  return { data, loading, error, reload, setData };
}
