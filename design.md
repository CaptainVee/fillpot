# Design Reference Prompt — Stitch by Google Aesthetic

Use this as your design system reference when building the website.

---

## Overall Aesthetic

Build a dark, minimal, AI-product-style website inspired by Google's Stitch tool. The design language is: **black background, white typography, animated particle/dot field, restrained use of color, and generous whitespace.**

---

## Background

- Base background: pure black (`#000000`) or near-black (`#080808`)
- Overlay a **dot/particle field** across the entire viewport:
  - Use a CSS radial-gradient dot pattern OR a `<canvas>` particle animation
  - Dots should be tiny (1–2px), white or very dark gray (`rgba(255,255,255,0.08)` to `rgba(255,255,255,0.15)`)
  - Spacing between dots: ~20–28px grid
  - The dots should feel like a subtle texture, not a loud grid
  - Optional: animate dots with a slow drift or pulse using `requestAnimationFrame`
- A soft **radial gradient glow** can be layered behind hero content (e.g. a faint white or indigo bloom at center, `rgba(255,255,255,0.04)`)

**CSS dot background pattern (static version):**
```css
background-color: #000;
background-image: radial-gradient(rgba(255,255,255,0.12) 1px, transparent 1px);
background-size: 24px 24px;
```

---

## Typography

- Font: `Inter`, `DM Sans`, or system sans-serif — clean and geometric
- Hero heading: 64–80px, `font-weight: 300` or `400` (light, not bold) — white (`#ffffff`)
- Subheadings: 20–24px, `font-weight: 400`, white or light gray (`#e0e0e0`)
- Body/supporting text: 14–16px, muted gray (`#888888` or `#aaaaaa`)
- All text in **sentence case**, never all-caps for body
- Letter-spacing on hero: `letter-spacing: -0.02em` for a tight, modern feel
- Line-height: `1.15` for large display text, `1.6` for body

---

## Color Palette

| Role | Value |
|------|-------|
| Background | `#000000` |
| Primary text | `#ffffff` |
| Secondary text | `#888888` |
| Muted text | `#555555` |
| Accent (subtle) | `rgba(255,255,255,0.06)` for card fills |
| Border | `rgba(255,255,255,0.1)` |
| Hover border | `rgba(255,255,255,0.25)` |
| CTA button bg | `#ffffff` |
| CTA button text | `#000000` |

Avoid heavy use of color. If you must accent, use a very desaturated indigo or white glow — never vibrant color blocks.

---

## Layout

- Max content width: `1100px`, centered with `margin: 0 auto`
- Hero section: vertically and horizontally centered, full viewport height (`100vh`)
- Generous padding: `80px` top/bottom on sections, `24px` horizontal on mobile
- Navigation: minimal top bar — logo left, 2–3 links right, no heavy borders. Use `backdrop-filter: blur(12px)` with `background: rgba(0,0,0,0.6)` for a frosted-glass nav on scroll.

---

## Components

### Hero Section
- Large wordmark or headline centered on screen
- One-line descriptor below in muted gray
- A single CTA button: white background, black text, `border-radius: 999px` (pill shape), `padding: 12px 28px`
- Optional: animated particle wave or ripple effect behind/below the headline

### Cards / Feature Blocks
- Background: `rgba(255,255,255,0.04)`
- Border: `1px solid rgba(255,255,255,0.08)`
- Border-radius: `16px`
- Hover state: border brightens to `rgba(255,255,255,0.18)`, subtle scale `transform: scale(1.01)`
- No drop shadows — border glow on hover only
- Icon: white, 24px, outline style

### Buttons
- **Primary:** `background: #fff`, `color: #000`, `border-radius: 999px`, no border
- **Secondary/Ghost:** `background: transparent`, `border: 1px solid rgba(255,255,255,0.2)`, `color: #fff`, `border-radius: 999px`
- Hover: subtle opacity shift or border brightness increase

### Navigation
- Logo: white wordmark, left-aligned
- Links: `color: #aaa`, hover `color: #fff`, no underline, `font-size: 15px`
- On scroll: nav gets `backdrop-filter: blur(12px)` + semi-transparent black bg

---

## Motion & Animation

- Keep animations **slow and subtle** — nothing jarring
- Particle field: dots drift slowly or pulse gently
- Hero text: fade-in on load with `opacity: 0 → 1`, `transform: translateY(12px) → 0`, duration `0.8s`, easing `ease-out`
- Card hover: `transition: border-color 0.2s ease, transform 0.2s ease`
- No bounce, no spring — smooth and calm

---

## What to Avoid

- No bright colors or gradients (except very subtle radial glows)
- No light backgrounds or white sections
- No heavy drop shadows
- No decorative borders or dividers (use whitespace instead)
- No all-caps text blocks
- No rounded corners smaller than `8px` or larger than `999px` (pill)
- No stock-photo imagery — keep it abstract and typographic

---

## Reference Mood

The site should feel like: **a premium AI tool product page** — calm, confident, dark, with just enough texture (the dot grid) and motion (particle field) to feel alive. Think Google Stitch, Vercel, Linear, or Anthropic's own landing pages.@