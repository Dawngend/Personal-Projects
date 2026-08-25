import { describe, expect, it } from "vitest";
import { GET } from "../app/health/route";

describe("web health endpoint", () => {
  it("returns the service health contract", async () => {
    const response = GET();

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ status: "ok", service: "web" });
  });
});
