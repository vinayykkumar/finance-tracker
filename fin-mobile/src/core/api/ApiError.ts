function detailToMessage(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((x) => {
      if (typeof x === "object" && x !== null && "msg" in x) {
        return String((x as { msg: unknown }).msg);
      }
      return JSON.stringify(x);
    });
    return parts.join("; ");
  }
  return null;
}

export function messageFromErrorBody(body: unknown, fallback: string): string {
  if (typeof body !== "object" || body === null) return fallback;
  const d = (body as { detail?: unknown }).detail;
  const m = detailToMessage(d);
  return m ?? fallback;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly body?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }

  static fromResponse(status: number, parsedBody: unknown, fallback: string): ApiError {
    return new ApiError(status, messageFromErrorBody(parsedBody, fallback), parsedBody);
  }
}
