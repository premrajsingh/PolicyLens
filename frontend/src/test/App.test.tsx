import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Layout from "../components/Layout";
import { formatBytes, formatPercent } from "../lib/api";

describe("Layout", () => {
  it("renders PolicyLens brand in navigation", () => {
    render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>,
    );
    expect(screen.getAllByText("PolicyLens").length).toBeGreaterThan(0);
  });
});

describe("api helpers", () => {
  it("formatBytes formats sizes correctly", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
  });

  it("formatPercent converts decimals to percentages", () => {
    expect(formatPercent(0.856)).toBe("86%");
  });
});
