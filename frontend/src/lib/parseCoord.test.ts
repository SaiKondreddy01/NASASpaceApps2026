import { describe, expect, it } from "vitest";
import { parseCoord } from "../components/SearchBar";

describe("parseCoord", () => {
  it("parses official WISE 0855 colon string", () => {
    const p = parseCoord("08:55:10.831 -07:14:42.53");
    expect(p).not.toBeNull();
    // 08h55m10.831s = 133.79512916…°
    expect(p!.ra).toBeCloseTo(133.79512917, 5);
    expect(p!.dec).toBeCloseTo(-7.24514722, 5);
  });

  it("parses degree pair", () => {
    const p = parseCoord("133.795, -7.245");
    expect(p?.ra).toBeCloseTo(133.795, 3);
    expect(p?.dec).toBeCloseTo(-7.245, 3);
  });
});
