import { describe, expect, it } from "vitest";

import { apiErrorMessage } from "./api";


describe("apiErrorMessage", () => {
  it("prefers the backend detail message", () => {
    expect(
      apiErrorMessage({
        message: "Request failed",
        response: { data: { detail: "Invalid operator key" } }
      })
    ).toBe("Invalid operator key");
  });
});
