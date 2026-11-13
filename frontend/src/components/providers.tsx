"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";
import { Toaster } from "sonner";
import { TooltipProvider } from "./ui/overlay";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(
    () => new QueryClient({
      defaultOptions: {
        queries: { staleTime: 10_000, retry: (n, e) => n < 1 && (e as { status?: number })?.status !== 404, refetchOnWindowFocus: false },
      },
    }),
  );
  // Shelfcraft is a local, data-driven app with no SEO needs: render it client-side only.
  // This avoids hydration mismatches when Suspense boundaries hydrate after data has loaded.
  const mounted = React.useSyncExternalStore(() => () => {}, () => true, () => false);
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        {mounted ? children : <BootSplash />}
        <Toaster position="bottom-right" richColors closeButton toastOptions={{ className: "!rounded-[12px] !text-[13px]" }} />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

function BootSplash() {
  return (
    <div className="flex h-full items-center justify-center" aria-busy="true" aria-label="Loading Shelfcraft">
      <div className="size-8 animate-pulse rounded-[9px] bg-primary/80" />
    </div>
  );
}

/** Error boundary so one broken panel never blanks the whole app. */
export class ErrorBoundary extends React.Component<{ children: React.ReactNode; label?: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error) {
    console.error("[Shelfcraft] UI error:", error);
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="m-6 rounded-[14px] border border-danger/30 bg-danger-soft p-5 text-[13px]">
        <div className="font-semibold text-danger">{this.props.label ?? "This section"} hit an unexpected error</div>
        <p className="mt-1 text-foreground/80">{this.state.error.message}</p>
        <p className="mt-1 text-muted">Your saved work is safe. Try again, or reload the page.</p>
        <button className="mt-3 rounded-[10px] border border-border-strong bg-surface px-3 py-1.5 font-medium hover:bg-sunken"
          onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}
