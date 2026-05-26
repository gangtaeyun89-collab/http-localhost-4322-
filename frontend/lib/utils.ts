import clsx, { type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// Tailwind-aware className combiner -- the standard shadcn helper. Lets a
// component override class names from its parent without duplicating them.
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

// Format a number with a fixed number of digits, signed, mono-friendly.
export function fmtNum(
  value: number | null | undefined,
  digits = 2,
  signed = false
): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = signed && value > 0 ? "+" : "";
  return sign + value.toFixed(digits);
}

export function fmtPct(
  value: number | null | undefined,
  digits = 2,
  signed = true
): string {
  if (value == null || Number.isNaN(value)) return "—";
  return fmtNum(value * 100, digits, signed) + "%";
}
