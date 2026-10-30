"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, api, type Health, type Item, type Page } from "@/lib/api";

function toMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.message} (${error.status})`;
  }
  return fallback;
}

export function ItemsExplorer() {
  const [items, setItems] = useState<Item[]>([]);
  const [total, setTotal] = useState(0);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [price, setPrice] = useState("0");
  const [submitting, setSubmitting] = useState(false);

  const fetchData = useCallback(async () => {
    const [page, apiHealth] = await Promise.all([api.items.list(), api.health()]);
    return { page, apiHealth };
  }, []);

  const applyData = useCallback((page: Page<Item>, apiHealth: Health) => {
    setItems(page.items);
    setTotal(page.total);
    setHealth(apiHealth);
    setError(null);
  }, []);

  useEffect(() => {
    let active = true;

    fetchData()
      .then(({ page, apiHealth }) => {
        if (active) applyData(page, apiHealth);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            toMessage(
              err,
              "Cannot reach the API. Is the backend running on port 8000?",
            ),
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [fetchData, applyData]);

  async function refresh() {
    const { page, apiHealth } = await fetchData();
    applyData(page, apiHealth);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;

    setSubmitting(true);
    try {
      await api.items.create({ name: name.trim(), price: Number(price) || 0 });
      setName("");
      setPrice("0");
      await refresh();
    } catch (err) {
      setError(toMessage(err, "Failed to create item"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await api.items.remove(id);
      await refresh();
    } catch (err) {
      setError(toMessage(err, "Failed to delete item"));
    }
  }

  return (
    <section className="flex w-full flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Items</h2>
        <span className="rounded-full border border-zinc-200 px-3 py-1 text-xs font-medium text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
          {health ? `API ${health.status} · v${health.version}` : "API offline"}
        </span>
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-3 rounded-xl border border-zinc-200 p-4 sm:flex-row sm:items-end dark:border-zinc-800"
      >
        <label className="flex flex-1 flex-col gap-1 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Name
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Notebook"
            className="rounded-lg border border-zinc-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700"
          />
        </label>
        <label className="flex w-full flex-col gap-1 text-sm font-medium text-zinc-700 sm:w-32 dark:text-zinc-300">
          Price
          <input
            type="number"
            min="0"
            step="0.01"
            value={price}
            onChange={(event) => setPrice(event.target.value)}
            className="rounded-lg border border-zinc-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700"
          />
        </label>
        <button
          type="submit"
          disabled={submitting}
          className="h-10 rounded-lg bg-zinc-900 px-5 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {submitting ? "Adding..." : "Add item"}
        </button>
      </form>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-sm text-zinc-500">Loading...</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-zinc-500">No items yet — add one above.</p>
      ) : (
        <ul className="divide-y divide-zinc-200 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
          {items.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-4 px-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-50">
                  {item.name}
                </p>
                <p className="text-xs text-zinc-500">
                  #{item.id} · ${item.price.toFixed(2)} · {item.is_active ? "active" : "inactive"}
                </p>
              </div>
              <button
                onClick={() => void handleDelete(item.id)}
                className="shrink-0 rounded-lg border border-zinc-300 px-3 py-1 text-xs font-medium text-zinc-600 transition-colors hover:border-red-400 hover:text-red-600 dark:border-zinc-700 dark:text-zinc-400"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-zinc-500">{total} item(s) in total</p>
    </section>
  );
}
