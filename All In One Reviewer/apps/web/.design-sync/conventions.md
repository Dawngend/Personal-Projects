# Proof Garden

The design system for AndyHub, a study platform. This is a **token system**, not a component library: there are no shipped components to compose with. Build layouts yourself and style every one of them from the tokens below. Never introduce a color, font, or radius that is not defined here.

Light only. There is no dark variant, and inventing one is wrong.

## Setup

No provider or wrapper is required. Import `styles.css` and the tokens are available on `:root`. The three typefaces load from a remote Google Fonts `@import` already present in the stylesheet, so do not add font links of your own.

## The styling idiom

Plain CSS custom properties, referenced as `var(--token)`. There are no utility classes, no theme prop system, and no class-name vocabulary to learn. If you need a class, author it and style it from these tokens.

**Core, 6 tokens:**

| Token | Role |
|---|---|
| `--graphite` | primary text, solid button fills |
| `--matrix-mist` | page background |
| `--orchid-ink` | primary accent, links, eyebrow labels |
| `--signal-amber` | focus ring, attention |
| `--vector-teal` | success, secondary accent |
| `--error-carmine` | error |

**Surfaces and washes, 7 tokens:** `--mist-paper` (raised surface), `--mist-deep` (recessed), `--mist-line` (hairline borders), `--orchid-wash`, `--teal-wash`, `--amber-wash`, `--carmine-wash` (tinted backgrounds pairing with the accent of the same name).

**Type, 3 tokens:** `--font-display` (Familjen Grotesk), `--font-body` (Atkinson Hyperlegible Next), `--font-mono` (IBM Plex Mono).

`--font-body` is an accessibility typeface, chosen deliberately for a study tool. Never substitute it for something more fashionable.

## Required patterns

**Display headings** run tight and large. This is the system's strongest visual signature:

```css
font-family: var(--font-display);
font-size: clamp(2.6rem, 6vw, 4.8rem);
letter-spacing: -0.075em;
line-height: 0.9;
```

**Eyebrow labels** above headings are mono, uppercase, orchid:

```css
font-family: var(--font-mono);
font-size: 0.68rem;
font-weight: 600;
letter-spacing: 0.11em;
text-transform: uppercase;
color: var(--orchid-ink);
```

**Page background** is never a flat fill. One soft orchid radial:

```css
background:
  radial-gradient(circle at 84% 5%, rgba(90, 62, 121, 0.11), transparent 29rem),
  var(--matrix-mist);
```

**Focus ring** is deliberately loud. Do not soften it:

```css
:focus-visible { outline: 3px solid var(--signal-amber); outline-offset: 3px; }
```

Separate surfaces with `--mist-line` hairlines and the wash tokens, not with drop shadows.

## Never do these

These are the defaults that make generated design recognizable as generated. They are forbidden here.

**Color.** No purple-to-blue gradient; indigo `#6366f1` into violet `#a855f7` is the strongest single tell. No blurred gradient blobs behind glassmorphic cards. No `#0f172a` slate background. No warm cream with terracotta. No near-black with acid green. No color absent from the token list above.

**Type.** No Inter as a default. No Poppins at all. Never one typeface at one size doing every job. Timid headings read as generated; use the display scale above.

**Layout.** No uniform corner radius on every element. No large drop shadow on every surface. No centered hero with a headline, a filled button, a ghost button, and three icon-title-paragraph cards beneath it; that is the default generated page. No perfectly even three-column feature grid, because asymmetry carries information. Nothing overlaps, and nothing touches a container edge.

**Ornament.** No emoji standing in for icons. No sparkle glyph for anything AI-related. Structure such as numbering, dividers, and grouping must encode real information or be removed.

**Copy inside designs.** No "seamlessly", "elevate", "unlock", "empower", "transform". No em dash used as a prose connector; use a colon, parentheses, a comma, or a full stop. Em dashes remain correct in figure captions and date ranges, and numeric ranges take an en dash.

## Where the truth lives

`styles.css` and its `@import` closure, principally `_ds_bundle.css`, hold every token definition and the base element styles. Read those files before styling rather than relying on this summary.
