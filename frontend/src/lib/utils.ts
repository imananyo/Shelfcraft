import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(n: number): string {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB"];
  const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
}

export function timeAgo(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.round(s / 86400)}d ago`;
  return d.toLocaleDateString();
}

export function uid(len = 10): string {
  const a = new Uint8Array(len);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => (b % 36).toString(36)).join("");
}

export const PROVIDER_LABELS: Record<string, string> = {
  ollama: "Ollama (local)", gemini: "Gemini", groq: "Groq", openrouter: "OpenRouter", cloudflare: "Cloudflare Workers AI",
  mistral: "Mistral", local_diffusion: "Local diffusion", rembg: "rembg (local)", lama: "LaMa (local)", opencv: "OpenCV",
  ffmpeg: "FFmpeg", shelfcraft: "Shelfcraft", fake: "Test provider",
};

export function providerLabel(p?: string | null) {
  return p ? (PROVIDER_LABELS[p] ?? p) : "";
}
