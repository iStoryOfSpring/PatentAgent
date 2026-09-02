// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getInitialLocale, I18nProvider, isLocale, localeFromLanguage, localeFromNavigator,
  LOCALE_STORAGE_KEY, persistLocale, readStoredLocale, translate, useI18n,
} from ".";
import { httpStatusLabel, localizeErrorMessage, metricLabel } from "../uiLabels";

function createMemoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => Array.from(values.keys())[index] ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => values.set(key, String(value)),
  } as Storage;
}

beforeEach(() => {
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: createMemoryStorage(),
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
  document.documentElement.lang = "zh-CN";
});

describe("locale detection and persistence", () => {
  it("accepts only the two supported persisted locales and prioritizes storage", () => {
    expect(isLocale("zh-CN")).toBe(true);
    expect(isLocale("en-US")).toBe(true);
    expect(isLocale("fr-FR")).toBe(false);
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    expect(getInitialLocale()).toBe("en-US");
  });

  it("maps browser language ranges in order and defaults unknown languages to Chinese", () => {
    expect(localeFromLanguage("zh-Hans-CN")).toBe("zh-CN");
    expect(localeFromLanguage("en-GB")).toBe("en-US");
    expect(localeFromNavigator(["fr-FR", "en-GB"])).toBe("en-US");
    expect(localeFromNavigator(["fr-FR", "ja-JP"])).toBe("zh-CN");
  });

  it("ignores invalid storage and survives storage read/write failures", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "fr-FR");
    expect(readStoredLocale()).toBeNull();

    vi.spyOn(window.localStorage, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readStoredLocale()).toBeNull();

    vi.restoreAllMocks();
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(() => persistLocale("en-US")).not.toThrow();
  });

  it("localizes stable client errors at render time without changing backend details", () => {
    expect(localizeErrorMessage("client.network", "zh-CN")).toContain("无法连接后端");
    expect(localizeErrorMessage("client.network", "en-US")).toContain("Cannot connect");
    expect(localizeErrorMessage("client.sse.invalidEvent", "en-US")).toContain("unparseable");
    expect(localizeErrorMessage("client.http.503", "en-US")).toBe("Service temporarily unavailable");
    const clientMessage = httpStatusLabel(418, "I'm a teapot");
    expect(localizeErrorMessage(clientMessage, "en-US")).toBe("Request failed (HTTP 418: I'm a teapot)");

    const backendMessage = "Upstream detail: patent gateway rejected request";
    expect(localizeErrorMessage(backendMessage, "en-US")).toBe(backendMessage);
  });

  it("localizes known schema labels but keeps unknown result values unchanged", () => {
    expect(metricLabel("IPC 标注次数", "en-US")).toBe("IPC assignments");
    expect(metricLabel("assignment_count", "en-US")).toBe("IPC assignments");
    expect(metricLabel("custom metric", "en-US")).toBe("custom metric");
  });
});

function LocaleProbe() {
  const { locale, setLocale, t } = useI18n();
  return <div>
    <span data-testid="locale">{locale}</span>
    <span data-testid="label">{t("nav.datasets")}</span>
    <button onClick={() => setLocale("en-US")}>switch</button>
  </div>;
}

describe("I18nProvider", () => {
  beforeEach(() => window.localStorage.setItem(LOCALE_STORAGE_KEY, "zh-CN"));

  it("switches immediately, persists the choice, updates html lang, and safely falls back", () => {
    render(<I18nProvider><LocaleProbe /></I18nProvider>);
    expect(screen.getByTestId("locale").textContent).toBe("zh-CN");
    expect(screen.getByTestId("label").textContent).toBe("数据集");
    fireEvent.click(screen.getByRole("button", { name: "switch" }));
    expect(screen.getByTestId("locale").textContent).toBe("en-US");
    expect(screen.getByTestId("label").textContent).toBe("Datasets");
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("en-US");
    expect(document.documentElement.lang).toBe("en-US");
    expect(translate("missing.translation.key", "en-US")).toBe("missing.translation.key");
  });

  it("keeps the in-memory locale when persistence is unavailable", () => {
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    render(<I18nProvider><LocaleProbe /></I18nProvider>);

    fireEvent.click(screen.getByRole("button", { name: "switch" }));

    expect(screen.getByTestId("locale").textContent).toBe("en-US");
    expect(screen.getByTestId("label").textContent).toBe("Datasets");
    expect(document.documentElement.lang).toBe("en-US");
  });
});
