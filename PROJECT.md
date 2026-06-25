# Project: NexusAI Theme & Layout Overhaul

## Architecture
- Custom CSS overrides are loaded automatically by Chainlit from `public/stylesheet.css`.
- Primary colors, fonts, and base styling are defined in `public/theme.json`.
- Layout structure uses Material UI (MUI) components (like `.MuiDrawer-paper`, `.message`, `.step`, `header`, footer, etc.).
- Login screens are hosted statically at `public/login/index.html` and `public/login/signup.html`.

## Milestones
| # | Name | Scope | Dependencies | Status | Conv ID |
|---|---|---|---|---|---|
| 1 | E2E Testing Track | Design and implement the test suite verifying CSS styling, selector properties, and port 8000 server responsiveness | None | IN_PROGRESS | ad4946d1-85b4-4913-a86b-1f3504f7d4d8 |
| 2 | Liquid Glass Frost Theme | Overhaul theme.json and stylesheet.css to match Liquid Glass Frost gradients, backgrounds, and font settings | M1 | IN_PROGRESS | 1c739666-de7c-46ab-a2be-1f72604f9e35 |
| 3 | Sidebar Overlap Fix | Override CSS classes to ensure sidebar does not overlap chat area and has appropriate z-index/paddings | M2 | IN_PROGRESS | 1c739666-de7c-46ab-a2be-1f72604f9e35 |
| 4 | Final E2E Pass & Audit | Run all tests, run Forensic Auditor, and perform final verification on live UI | M3 | PLANNED | TBD |

## Interface Contracts
### stylesheet.css ↔ Chainlit UI
- Custom CSS must override default Chainlit styles without breaking interactivity or layout.
- Specific overrides: `.MuiDrawer-paper` (or equivalent sidebar container) must have proper padding/z-index.
- `.message` or `.step` elements must contain cyan-violet gradient values.
- Dark frosted backgrounds and glass effects (`backdrop-filter: blur(...)`) must be styled properly.

## Code Layout
- `public/stylesheet.css`: Core CSS overrides for Chainlit.
- `public/theme.json`: JSON configuration for Chainlit light/dark themes.
- `public/login/index.html`: Reference styling for "Liquid Glass Frost".
