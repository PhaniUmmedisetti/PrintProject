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
  failure_code: string | null;
  retryable: boolean | null;
  file_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface KioskErrorState {
  title: string;
  message: string;
  retryLabel?: string;
  cancelLabel?: string;
  retryTarget?: "KEYPAD" | "LANDING";
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
  if (res.status === 409) {
    const payload = await res.json();
    throw new PrinterNotReadyError(String(payload.detail ?? "Printer not ready"));
  }
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
    super("Invalid code");
  }
}

export class PrinterNotReadyError extends Error {
  constructor(message: string) {
    super(message);
  }
}

export function buildJobFailureError(status: Pick<JobStatus, "error_msg" | "failure_code" | "retryable">): KioskErrorState {
  const baseMessage = String(status.error_msg ?? "Printing failed.");

  if (status.retryable) {
    const issue =
      status.failure_code === "PAPER_JAM"
        ? "The printer jammed before your full document finished."
        : status.failure_code === "PAPER_OUT"
          ? "The printer ran out of paper before your full document finished."
        : status.failure_code === "DOOR_OPEN"
            ? "The printer was opened before your full document finished."
          : status.failure_code === "CARTRIDGE_MISSING"
              ? "The printer cartridge needs attention before your full document can finish."
            : status.failure_code === "INK_EMPTY"
                ? "The printer ran out of ink before your full document finished."
              : status.failure_code === "UNVERIFIED_COMPLETION"
                ? "The kiosk could not verify whether every page finished printing."
                : status.failure_code === "DOWNLOAD_FAILED"
                  ? "The file could not be prepared for printing."
                  : "Printing stopped before your full document finished.";

    if (status.failure_code === "UNVERIFIED_COMPLETION") {
      return {
        title: "Print Not Confirmed",
        message: `${issue} If your full document already came out, tap Printed OK and do not retry. If nothing printed or pages are missing, use the same OTP again.`,
        retryLabel: "Use Same OTP",
        cancelLabel: "Printed OK",
        retryTarget: "KEYPAD",
      };
    }

    return {
      title: "Print Interrupted",
      message: `${issue} Your same OTP is still valid. Use it again to print from the start.`,
      retryLabel: "Use Same OTP",
      cancelLabel: "Home",
      retryTarget: "KEYPAD",
    };
  }

  return {
    title: "Printing Failed",
    message: baseMessage,
    retryLabel: "Try Again",
    cancelLabel: "Home",
    retryTarget: "KEYPAD",
  };
}

export function buildSimpleError(
  title: string,
  message: string,
  options?: Partial<Pick<KioskErrorState, "retryLabel" | "cancelLabel" | "retryTarget">>,
): KioskErrorState {
  return {
    title,
    message,
    retryLabel: options?.retryLabel ?? "Try Again",
    cancelLabel: options?.cancelLabel ?? "Home",
    retryTarget: options?.retryTarget ?? "KEYPAD",
  };
}
