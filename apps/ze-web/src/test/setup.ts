import "@testing-library/jest-dom/vitest";

// jsdom has no ResizeObserver — required by @xyflow/react's viewport sizing.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
