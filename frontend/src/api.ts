// Client for the canonical fix_explainer FastAPI backend.
// All requests use relative paths; the Vite dev proxy forwards /api to :8000.

export interface KnownFactField {
  tag: number;
  value: string;
  ordinal: number;
  evidence_tags?: number[];
  field_name?: string;
  enum_name?: string;
}

export interface KnownFact {
  claim: string;
  field?: KnownFactField;
  evidence_tags?: number[];
  evidence_fields?: { tag: number; ordinal: number }[];
  specification?: string;
}

export interface ValidationFinding {
  code: string;
  message: string;
  severity: string;
  tag: number | null;
  ordinal: number | null;
}

export interface MessageFieldEntry {
  tag: number;
  value: string;
  raw_value_hex: string;
  ordinal: number;
  start_offset: number;
  end_offset: number;
}

export interface BackendMessage {
  message_type: string;
  fields: MessageFieldEntry[];
}

export interface ExplainResponse {
  provider: 'template' | 'gemini';
  provider_summary: string;
  fallback_used: boolean;
  fallback_reason: string | null;
  deterministic: {
    known_facts: KnownFact[];
    inferred_context: unknown[];
    unknowns: string[];
    validation_errors: ValidationFinding[];
  };
  message: BackendMessage;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function explainViaApi(message: string): Promise<ExplainResponse> {
  const resp = await fetch('/api/explain', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  const data: unknown = await resp.json().catch(() => null);
  if (!resp.ok) {
    const detail =
      data && typeof data === 'object' && 'error' in data && typeof data.error === 'string'
        ? data.error
        : `API error ${resp.status}`;
    throw new ApiError(resp.status, detail);
  }
  if (!data || typeof data !== 'object' || !('deterministic' in data) || !('provider_summary' in data)) {
    throw new ApiError(502, 'Backend response schema mismatch. Start the current FastAPI backend.');
  }
  return data as ExplainResponse;
}
