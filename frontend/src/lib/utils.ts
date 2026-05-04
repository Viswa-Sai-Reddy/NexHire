import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Tailwind class merger. Convention used by every shadcn/ui component.
 * Last value wins on conflicts: `cn("p-2", "p-4")` → `"p-4"`.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
