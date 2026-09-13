import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MathText, splitMathText } from "../components/notes/math-text";

describe("note math text", () => {
  it("splits dollar and parenthesized inline math", () => {
    expect(splitMathText("Let $x_1$ equal \\(y+1\\).")).toEqual([
      { kind: "text", source: "Let " },
      { kind: "math", source: "x_1", display: false },
      { kind: "text", source: " equal " },
      { kind: "math", source: "y+1", display: false },
      { kind: "text", source: "." },
    ]);
  });

  it("splits dollar and bracketed display math", () => {
    expect(splitMathText("First $$x^2$$ then \\[y^2\\].")).toEqual([
      { kind: "text", source: "First " },
      { kind: "math", source: "x^2", display: true },
      { kind: "text", source: " then " },
      { kind: "math", source: "y^2", display: true },
      { kind: "text", source: "." },
    ]);
  });

  it("treats a bare matrix environment as display math", () => {
    const matrix = "\\begin{bmatrix}1 & 2\\\\3 & 4\\end{bmatrix}";
    expect(splitMathText(`Given A = ${matrix}, find its size.`)).toEqual([
      { kind: "text", source: "Given A = " },
      { kind: "math", source: matrix, display: true },
      { kind: "text", source: ", find its size." },
    ]);
  });

  it("does not interpret a literal price as math", () => {
    expect(splitMathText("It costs $5 per unit.")).toEqual([
      { kind: "text", source: "It costs $5 per unit." },
    ]);
  });

  it("renders a bare subscript emitted inside prose", () => {
    expect(splitMathText("The value a_{ij} at row i, column j.")).toEqual([
      { kind: "text", source: "The value " },
      { kind: "math", source: "a_{ij}", display: false },
      { kind: "text", source: " at row i, column j." },
    ]);
  });

  it("shows malformed math source without throwing", () => {
    const malformed = "Value: $\\frac{1}{$";
    expect(() => renderToStaticMarkup(createElement(MathText, null, malformed))).not.toThrow();
    expect(renderToStaticMarkup(createElement(MathText, null, malformed))).toContain("\\frac{1}{");
  });
});
