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

interface RetryableErrorPayload {
  message?: string;
  failureCode?: string;
  retryable?: boolean;
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
    throw buildPrinterAttentionException(payload.detail);
  }

  if (!res.ok) throw new Error(`Server error: ${res.status}`);
  return res.json();
}

export async function confirmPrint(jobId: string): Promise<void> {
  const res = await fetch(`${BASE}/local/confirm/${jobId}`, { method: "POST" });
  if (res.status === 409) {
    const payload = await res.json();
    throw buildPrinterAttentionException(payload.detail);
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
  failureCode: string;
  retryable: boolean;

  constructor(message: string, failureCode = "PRINTER_NOT_READY", retryable = true) {
    super(message);
    this.failureCode = failureCode;
    this.retryable = retryable;
  }
}

function buildPrinterAttentionException(detail: unknown): PrinterNotReadyError {
  if (detail && typeof detail === "object") {
    const typed = detail as RetryableErrorPayload;
    return new PrinterNotReadyError(
      String(typed.message ?? "Printer not ready"),
      String(typed.failureCode ?? "PRINTER_NOT_READY"),
      typed.retryable !== false,
    );
  }

  return new PrinterNotReadyError(String(detail ?? "Printer not ready"));
}

function describeFailureCode(failureCode: string | null | undefined): { title: string; issue: string } {
  switch (failureCode) {
    case "PAPER_OUT":
      return {
        title: "Load Paper",
        issue: "The printer is out of paper, so nothing else can print until paper is loaded.",
      };
    case "PAPER_JAM":
      return {
        title: "Paper Jam",
        issue: "The printer jammed before your full document finished printing.",
      };
    case "DOOR_OPEN":
      return {
        title: "Close Printer Cover",
        issue: "The printer cover is open, so the job cannot finish.",
      };
    case "CARTRIDGE_MISSING":
      return {
        title: "Printer Cartridge Issue",
        issue: "The printer cartridge needs attention before your document can finish.",
      };
    case "INK_EMPTY":
      return {
        title: "Printer Out Of Ink",
        issue: "The printer ran out of ink before your full document finished.",
      };
    case "INK_LOW":
      return {
        title: "Printer Needs Attention",
        issue: "The printer reports low ink and could not complete this document reliably.",
      };
    case "DOWNLOAD_FAILED":
      return {
        title: "File Could Not Be Prepared",
        issue: "The kiosk could not prepare your file for printing.",
      };
    case "UNVERIFIED_COMPLETION":
      return {
        title: "Print Not Confirmed",
        issue: "The kiosk could not verify whether every page finished printing.",
      };
    case "PARTIAL_PRINT":
      return {
        title: "Print Interrupted",
        issue: "The printer did not finish the full document.",
      };
    case "PRINTER_NOT_READY":
      return {
        title: "Printer Needs Attention",
        issue: "The printer is not ready to accept this job yet.",
      };
    default:
      return {
        title: "Printing Failed",
        issue: "Printing stopped before your full document finished.",
      };
  }
}

export function buildJobFailureError(status: Pick<JobStatus, "error_msg" | "failure_code" | "retryable">): KioskErrorState {
  const baseMessage = String(status.error_msg ?? "Printing failed.");
  const { title, issue } = describeFailureCode(status.failure_code);

  if (status.retryable) {
    if (status.failure_code === "UNVERIFIED_COMPLETION") {
      return {
        title,
        message: `${issue} If your full document already came out, tap Printed OK and do not retry. If nothing printed or pages are missing, use the same OTP again.`,
        retryLabel: "Use Same OTP",
        cancelLabel: "Printed OK",
        retryTarget: "KEYPAD",
      };
    }

    return {
      title,
      message: `${issue} Your same OTP is still valid. Use it again to print from the start.`,
      retryLabel: "Use Same OTP",
      cancelLabel: "Home",
      retryTarget: "KEYPAD",
    };
  }

  return {
    title,
    message: baseMessage,
    retryLabel: "Try Again",
    cancelLabel: "Home",
    retryTarget: "KEYPAD",
  };
}

export function buildPrinterAttentionError(error: PrinterNotReadyError): KioskErrorState {
  const { title, issue } = describeFailureCode(error.failureCode);

  if (error.retryable) {
    return {
      title,
      message: `${issue} Your same OTP is still valid. Fix the printer issue, then use the same OTP again.`,
      retryLabel: "Use Same OTP",
      cancelLabel: "Home",
      retryTarget: "KEYPAD",
    };
  }

  return {
    title,
    message: error.message,
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
