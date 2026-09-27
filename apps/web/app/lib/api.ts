// Thin client for the backend (apps/server). Every function maps to exactly
// one endpoint; callers own the UI state around it.
import { API_URL } from "./constants";
import { readSseEvents } from "./sse";
import type {
  BrandPack,
  Deck,
  DeckAudit,
  GenerationRequest,
  InspectedTemplate,
  Outline,
  PreviewStatus,
  StageStatus,
  TaskMaterials,
  TemplateInfo,
} from "./types";

// FastAPI puts the reason in `detail`; fall back to the HTTP status line.
async function responseError(res: Response): Promise<Error> {
  const err = await res.json().catch(() => ({}));
  return new Error(err.detail ?? `${res.status} ${res.statusText}`);
}

function postJson(path: string, body: unknown): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchTemplates(): Promise<{ templates: TemplateInfo[] }> {
  return fetch(`${API_URL}/api/templates`).then((r) => r.json());
}

export function templatePreviewUrl(templateId: string, n: number): string {
  return `${API_URL}/api/templates/${encodeURIComponent(templateId)}/preview/${n}`;
}

export async function uploadTemplate(file: File): Promise<{ id: string; label: string }> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${API_URL}/api/templates`, { method: "POST", body });
  if (!res.ok) throw await responseError(res);
  return (await res.json()) as { id: string; label: string };
}

export function inspectTemplate(templateId: string): Promise<InspectedTemplate> {
  return fetch(`${API_URL}/api/templates/${encodeURIComponent(templateId)}/inspect`).then((r) =>
    r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)),
  );
}

export function fetchBrandPacks(): Promise<{ packs: BrandPack[] }> {
  return fetch(`${API_URL}/api/brand-packs`).then((r) => r.json());
}

export async function uploadBrandPack(name: string, file: File): Promise<BrandPack> {
  const body = new FormData();
  body.append("name", name);
  body.append("file", file);
  const res = await fetch(`${API_URL}/api/brand-packs`, { method: "POST", body });
  if (!res.ok) throw await responseError(res);
  return (await res.json()) as BrandPack;
}

// Materials become text on the server (no LLM, seconds); generation
// requests then only carry the resulting id.
export async function uploadMaterials(m: TaskMaterials): Promise<string> {
  const body = new FormData();
  body.append("story", m.story);
  for (const f of m.files) body.append("files", f);
  const res = await fetch(`${API_URL}/api/sources`, { method: "POST", body });
  if (!res.ok) throw await responseError(res);
  const { id } = (await res.json()) as { id: string };
  return id;
}

export async function requestOutline(request: GenerationRequest): Promise<Outline> {
  const res = await postJson("/api/outline", request);
  if (!res.ok) throw await responseError(res);
  return (await res.json()) as Outline;
}

// Real progress from the backend: each `stage` event fires the moment
// that stage actually starts/finishes on the server, not a guessed
// local approximation. Stream ends with either `result` or `error`.
export async function streamAudit(
  request: GenerationRequest & { outline: Outline | null },
  onStage: (stage: string, status: StageStatus) => void,
): Promise<DeckAudit> {
  const res = await postJson("/api/audit/stream", request);
  if (!res.ok || !res.body) throw await responseError(res);

  let audit: DeckAudit | null = null;
  let streamError: string | null = null;
  for await (const { event, data } of readSseEvents(res.body)) {
    const payload = JSON.parse(data);
    if (event === "stage") {
      onStage(payload.stage, payload.status);
    } else if (event === "result") {
      audit = payload as DeckAudit;
    } else if (event === "error") {
      streamError = payload.detail ?? "unknown error";
    }
  }

  if (streamError) throw new Error(streamError);
  if (!audit) throw new Error("stream ended without a result");
  return audit;
}

// The exported .pptx rendered to images by the server (LibreOffice). 501
// means the server has no renderer installed.
export async function renderPreview(deck: Deck): Promise<{ images: string[] | null; status: PreviewStatus }> {
  const res = await postJson("/api/preview", deck);
  if (res.status === 501) return { images: null, status: "unavailable" };
  if (!res.ok) return { images: null, status: "error" };
  const data = (await res.json()) as { slides: string[] };
  return { images: data.slides, status: "ready" };
}

export async function exportDeck(deck: Deck): Promise<Blob> {
  const res = await postJson("/api/export", deck);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.blob();
}
