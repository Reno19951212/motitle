export class ApiError extends Error {
  constructor(message: string, public status: number, public body: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

export class UnauthorizedError extends ApiError {
  constructor() {
    super('Unauthorized', 401, null);
    this.name = 'UnauthorizedError';
  }
}

export async function apiFetch<T = unknown>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (response.status === 401) throw new UnauthorizedError();
  if (!response.ok) {
    let body: unknown = null;
    let msg = `HTTP ${response.status}`;
    try {
      body = await response.json();
      if (body && typeof body === 'object' && 'error' in body) msg = String((body as { error: unknown }).error);
    } catch { /* not JSON */ }
    throw new ApiError(msg, response.status, body);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
