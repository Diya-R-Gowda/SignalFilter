import type { Item } from "./types";

export const isLowRelevance = (item: Item): boolean =>
  !item.passed_stage1 || (item.llm_score !== null && item.llm_score <= 1);

export const isDigestWorthy = (item: Item): boolean =>
  item.passed_stage1 &&
  item.llm_score !== null &&
  item.llm_score > 1 &&
  !item.notified &&
  item.digested_at === null &&
  item.queued_at === null;

export const isQueued = (item: Item): boolean => item.queued_at !== null;

export function splitItems(items: Item[]) {
  return {
    surfaced: items.filter((item) => item.notified),
    queued: items.filter(isQueued),
    filtered: items.filter((item) => !item.notified && !isQueued(item)),
    digest: items.filter(isDigestWorthy),
  };
}
