import { describe, it, expect, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useLoadMore } from "./use-load-more";

type Page = { items: string[]; next_cursor: string | null };

describe("useLoadMore", () => {
  it("appends the next page using the cursor and stops when there is none", async () => {
    const fetchPage = vi.fn<(cursor: string) => Promise<Page>>().mockResolvedValue({ items: ["c", "d"], next_cursor: null });
    const base = ["a", "b"];
    const { result } = renderHook(() => useLoadMore(base, "cur1", fetchPage));
    expect(result.current.items).toEqual(["a", "b"]);
    expect(result.current.hasMore).toBe(true);
    await act(async () => {
      await result.current.loadMore();
    });
    expect(fetchPage).toHaveBeenCalledWith("cur1");
    expect(result.current.items).toEqual(["a", "b", "c", "d"]);
    expect(result.current.hasMore).toBe(false);
  });

  it("follows chained cursors", async () => {
    const fetchPage = vi
      .fn<(cursor: string) => Promise<Page>>()
      .mockResolvedValueOnce({ items: ["c"], next_cursor: "cur2" })
      .mockResolvedValueOnce({ items: ["d"], next_cursor: null });
    const base = ["a"];
    const { result } = renderHook(() => useLoadMore(base, "cur1", fetchPage));
    await act(async () => {
      await result.current.loadMore();
    });
    await act(async () => {
      await result.current.loadMore();
    });
    expect(fetchPage.mock.calls.map((c) => c[0])).toEqual(["cur1", "cur2"]);
    expect(result.current.items).toEqual(["a", "c", "d"]);
  });

  it("reports failure without throwing and keeps the loaded items", async () => {
    const fetchPage = vi.fn<(cursor: string) => Promise<Page>>().mockRejectedValue(new Error("boom"));
    const base = ["a"];
    const { result } = renderHook(() => useLoadMore(base, "cur1", fetchPage));
    await act(async () => {
      await result.current.loadMore();
    });
    expect(result.current.failed).toBe(true);
    expect(result.current.items).toEqual(["a"]);
    expect(result.current.hasMore).toBe(true);
  });

  it("resets appended pages when the base list is reloaded", async () => {
    const fetchPage = vi.fn<(cursor: string) => Promise<Page>>().mockResolvedValue({ items: ["c"], next_cursor: null });
    const { result, rerender } = renderHook(({ base }) => useLoadMore(base, "cur1", fetchPage), {
      initialProps: { base: ["a"] },
    });
    await act(async () => {
      await result.current.loadMore();
    });
    expect(result.current.items).toEqual(["a", "c"]);
    rerender({ base: ["z"] });
    await waitFor(() => expect(result.current.items).toEqual(["z"]));
    expect(result.current.hasMore).toBe(true);
  });

  it("has nothing to load when the base cursor is null or data is missing", () => {
    const fetchPage = vi.fn();
    const { result } = renderHook(() => useLoadMore<string>(undefined, null, fetchPage));
    expect(result.current.items).toEqual([]);
    expect(result.current.hasMore).toBe(false);
  });
});
