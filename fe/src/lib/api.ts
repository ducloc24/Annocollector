const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export type Health = {
  status: string;
  environment: string;
  version: string;
};

export type Item = {
  id: number;
  name: string;
  description: string | null;
  price: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type ItemInput = {
  name: string;
  description?: string | null;
  price?: number;
  is_active?: boolean;
};

export type ListItemsParams = {
  offset?: number;
  limit?: number;
  search?: string;
  is_active?: boolean;
};

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      body?.message ?? response.statusText,
      response.status,
      body?.code,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  items: {
    list: (params: ListItemsParams = {}) => {
      const query = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) query.set(key, String(value));
      });
      const suffix = query.size > 0 ? `?${query.toString()}` : "";
      return request<Page<Item>>(`/items${suffix}`);
    },
    get: (id: number) => request<Item>(`/items/${id}`),
    create: (input: ItemInput) =>
      request<Item>("/items", { method: "POST", body: JSON.stringify(input) }),
    update: (id: number, input: Partial<ItemInput>) =>
      request<Item>(`/items/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
    remove: (id: number) => request<void>(`/items/${id}`, { method: "DELETE" }),
  },
};
