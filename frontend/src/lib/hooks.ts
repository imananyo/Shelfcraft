"use client";
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { ApiError, get, post } from "./api";
import type { Brand, Job, ProviderStatus, Settings } from "./types";

export function useApi<T>(key: QueryKey, path: string | null, opts: { refetchInterval?: number | false; enabled?: boolean } = {}) {
  return useQuery<T, ApiError>({
    queryKey: key,
    queryFn: () => get<T>(path!),
    enabled: path !== null && (opts.enabled ?? true),
    refetchInterval: opts.refetchInterval,
  });
}

export function useSettings() {
  return useApi<Settings>(["settings"], "/settings");
}

export function useBrands() {
  return useApi<Brand[]>(["brands"], "/brands");
}

export function useActiveBrand() {
  const s = useSettings();
  const b = useBrands();
  const active = b.data?.find((x) => x.id === s.data?.active_brand_id) ?? b.data?.[0] ?? null;
  return { brand: active, brands: b.data ?? [], isLoading: s.isLoading || b.isLoading };
}

export function useProviders() {
  return useApi<ProviderStatus[]>(["providers"], "/providers");
}

export function useCapabilities() {
  return useApi<{ text_ai: boolean; image_ai: boolean; local_diffusion_installed: boolean; background_removal: boolean;
    object_removal_ai: boolean; video: boolean }>(["capabilities"], "/capabilities", { refetchInterval: 30000 });
}

/** Poll a job until it finishes; fires callbacks once. */
export function useJob(jobId: string | null | undefined, cb?: { onDone?: (j: Job) => void; onFail?: (j: Job) => void }) {
  const qc = useQueryClient();
  const fired = useRef<string | null>(null);
  const q = useQuery<Job, ApiError>({
    queryKey: ["job", jobId],
    queryFn: () => get<Job>(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "succeeded" || s === "failed" || s === "cancelled" ? false : 1200;
    },
  });
  useEffect(() => {
    const j = q.data;
    if (!j || fired.current === `${j.id}:${j.status}`) return;
    if (j.status === "succeeded") {
      fired.current = `${j.id}:${j.status}`;
      qc.invalidateQueries({ queryKey: ["jobs"] });
      cb?.onDone?.(j);
    } else if (j.status === "failed") {
      fired.current = `${j.id}:${j.status}`;
      cb?.onFail?.(j);
    }
  }, [q.data, cb, qc]);
  return q;
}

export function useInvalidate() {
  const qc = useQueryClient();
  return (...keys: QueryKey[]) => keys.forEach((k) => qc.invalidateQueries({ queryKey: k }));
}

/** Mutation that shows a toast on error; returns typed data. */
export function useAction<TVars, TData = unknown>(fn: (v: TVars) => Promise<TData>, opts: { success?: string; onSuccess?: (d: TData, v: TVars) => void } = {}) {
  return useMutation<TData, ApiError, TVars>({
    mutationFn: fn,
    onSuccess: (d, v) => {
      if (opts.success) toast.success(opts.success);
      opts.onSuccess?.(d, v);
    },
    onError: (e) => toast.error(e.message),
  });
}

export const activateBrand = (id: string) => post(`/brands/${id}/activate`);
