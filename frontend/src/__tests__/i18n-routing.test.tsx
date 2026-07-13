import { routing } from "@/i18n/routing";
import en from "../../messages/en.json";
import vi from "../../messages/vi.json";

describe("i18n configuration", () => {
  it("declares exactly en (default) and vi", () => {
    expect(routing.locales).toEqual(["en", "vi"]);
    expect(routing.defaultLocale).toBe("en");
  });

  it("vi covers every key en has (no missing translations)", () => {
    function keys(obj: Record<string, unknown>, prefix = ""): string[] {
      return Object.entries(obj).flatMap(([k, v]) =>
        typeof v === "object" && v !== null
          ? keys(v as Record<string, unknown>, `${prefix}${k}.`)
          : [`${prefix}${k}`]
      );
    }
    expect(keys(vi).sort()).toEqual(keys(en).sort());
  });
});
