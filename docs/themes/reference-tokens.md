# Theme Token Reference

## Token Categories

## Core Surfaces
- `canvas`: app background behind primary surfaces
- `surface_0`: base panel surface
- `surface_1`: raised panel rows/cards
- `surface_2`: hover/selected container surface
- `surface_3`: stronger selection/input highlight surface

## Borders and Lines
- `line_soft`: subtle borders and separators
- `line_strong`: stronger hover or focused edges

## Text
- `text_primary`: default readable text
- `text_muted`: secondary labels and metadata
- `text_dim`: disabled/de-emphasized text

## Accent and Interaction
- `accent`: primary action color
- `accent_hover`: hover state for accent elements
- `accent_press`: pressed state for accent elements
- `accent_subtle`: muted accent background for badges and disabled accents
- `focus_ring`: keyboard focus outline color

## Status
- `danger`: destructive or error indicators
- `success`: success indicators and positive states

## Accessibility Guidance
- Keep `text_primary` high contrast against `surface_0`.
- Keep `text_muted` readable against `surface_0` and `surface_1`.
- Ensure `focus_ring` is clearly visible against both `surface_0` and `surface_2`.
- Avoid using accent colors that are too close to background tones.

## Practical Contrast Targets
- Body text against surfaces: aim for strong contrast (roughly WCAG AA or better).
- Muted metadata: keep readable, not decorative-only.
- Disabled text: visibly distinct but still legible.

## Recommended Workflow
1. Set surfaces first (`canvas`, `surface_0..3`).
2. Set text tokens for readability.
3. Set borders (`line_soft`, `line_strong`).
4. Set interaction colors (`accent`, `focus_ring`).
5. Validate with real screens (Source, Tag Editor, Auto-Tag, Artwork, Sync, Duplicates).
