# Theme Token Reference

Use this file as your "what does each token change?" reference.

## Token Effects
| Token | Main UI Impact | Examples |
|---|---|---|
| `canvas` | App-level background color | Main window background, menu bar base, status strip base |
| `surface_0` | Primary surface color | Input controls, menus, list/table base, album cover background |
| `surface_1` | Secondary raised surface | Buttons, cards, alternating rows, hover backgrounds |
| `surface_2` | Interactive highlight surface | Selected rows, focused nav items, hover states |
| `surface_3` | Stronger input selection color | Text selection background in editable fields |
| `line_soft` | Standard border/separator color | Control borders, card borders, split lines |
| `line_strong` | Stronger hover/active border color | Album card hover border, scrollbar hover handle |
| `text_primary` | Primary readable text color | Main labels, titles, body text |
| `text_muted` | Secondary metadata text color | Sub-labels, headers, durations, status details |
| `text_dim` | De-emphasized/disabled text color | Disabled button text, muted status notes |
| `accent` | Primary action/selection color | Accent buttons, active nav/selection bars, progress chunks |
| `accent_hover` | Hover state for accent elements | Accent button hover, selected badge foreground |
| `accent_press` | Pressed state for accent elements | Accent button pressed |
| `accent_subtle` | Muted accent background | Accent disabled background, selected badge background |
| `focus_ring` | Keyboard focus indicator color | Focus borders on inputs/buttons, focused row edge |
| `danger` | Reserved status token (required, currently not heavily used in QSS) | Future destructive/error visuals |
| `success` | Reserved status token (required, currently not heavily used in QSS) | Future success visuals |

## Token Groups
## Layout and Depth
- `canvas`
- `surface_0`
- `surface_1`
- `surface_2`
- `surface_3`

## Structure
- `line_soft`
- `line_strong`

## Typography
- `text_primary`
- `text_muted`
- `text_dim`

## Interaction
- `accent`
- `accent_hover`
- `accent_press`
- `accent_subtle`
- `focus_ring`

## Status
- `danger`
- `success`

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
