const BASE: string = import.meta.env.VITE_PI_API_URL ?? "http://localhost:8001";

export interface JobSummary {
  copies: number;
  color: string;
  priceCents: number;
  currency: string;
}

export interface StartPrintResponse {
  job_id: string;
  status: string;
  job_summary: JobSummary;
}

export interface JobStatus {
  id: string;
  status: "DOWNLOADING" | "CONVERTING" | "READY" | "PRINTING" | "DONE" | "FAILED";
  file_token: string | null;
  printer_name: string | null;
  job_summary: JobSummary | null;
  cups_job_id: string | null;
  error_msg: string | null;
  file_path: string | null;
  created_at: string;
  updated_at: string;
}

export async function startPrint(code: string): Promise<StartPrintResponse> {
  const res = await fetch(`${BASE}/local/print`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });

  if (res.status === 404) throw new InvalidCodeError();

  if (res.status === 409) {
    const payload = await res.json();
    throw new PrinterNotReadyError(String(payload.detail ?? "Printer not ready"));
  }

  if (!res.ok) throw new Error(`Server error: ${res.status}`);
  return res.json();
}

export async function confirmPrint(jobId: string): Promise<void> {
  const res = await fetch(`${BASE}/local/confirm/${jobId}`, { method: "POST" });
  if (!res.ok) throw new Error(`Confirm failed: ${res.status}`);
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE}/local/status/${jobId}`);
  if (!res.ok) throw new Error(`Status fetch failed: ${res.status}`);
  return res.json();
}

export async function getPrinters(): Promise<Record<string, string>> {
  const res = await fetch(`${BASE}/local/printers`);
  if (!res.ok) return {};
  const data = await res.json();
  return data.printers as Record<string, string>;
}

export class InvalidCodeError extends Error {
  constructor() {
    super("Invalid or expired code");
  }
}

export class PrinterNotReadyError extends Error {
  constructor(message: string) {
    super(message);
  }
}
