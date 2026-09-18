const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api';

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('bookclub_token');
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  const payload = await response.json().catch(() => ({})) as { error?: string };
  if (!response.ok) throw new ApiError(response.status, payload.error ?? 'Something went wrong');
  return payload as T;
}

export const json = (body: unknown): Pick<RequestInit, 'body'> => ({ body: JSON.stringify(body) });

