# E2E Test Infra: NexusAI Theme & Layout Overhaul

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on implementation design.
- Methodology: CSS Parsing + AST verification + Server checking.

## Feature Inventory
| # | Feature | Source (requirement) | Tier 1 (Feature) | Tier 2 (Boundary) | Tier 3 (Cross-Feature) | Tier 4 (Real-World) |
|---|---|---|:---:|:---:|:---:|:---:|
| 1 | Theme Color Aesthetic | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ | ✓ |
| 2 | Sidebar Overlap Prevention | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ | ✓ |
| 3 | Server Launch and Health | ORIGINAL_REQUEST Verification | 5 | 5 | ✓ | ✓ |

## Test Cases Design
### Tier 1: Feature Coverage
- Verify `public/stylesheet.css` defines `--nexus-cyan`, `--nexus-violet`, glass/frost backgrounds.
- Verify `public/theme.json` has correct dark theme configuration.
- Verify message / step class styling overrides exist in `stylesheet.css`.
- Verify scrollbar styling overrides exist in `stylesheet.css`.
- Verify code blocks override styling exists.

### Tier 2: Boundary & Corner Cases
- Verify sidebar class (`.MuiDrawer-paper` or equivalent) has `backdrop-filter: blur` and check for z-index value.
- Verify layout selector is modified to have padding/margin properties preventing layout overlap.
- Check font imports are not broken.
- Verify stylesheet uses valid CSS syntax (no malformed brackets/semicolons).
- Verify server launch returns HTML response (checks on port 8000 or 8000/public/stylesheet.css).

### Tier 3: Cross-Feature Combinations
- Verify the coexistence of background gradients and glass frost panels.
- Verify sidebar responsive width does not clash with the chat area content wrapper at different widths.

### Tier 4: Real-World Application Scenarios
- Launch the Chainlit app using `chainlit run app.py`, perform HTTP GET requests to check status, verify stylesheet links, and ensure zero frontend compilation or backend startup errors.

## Test Architecture
- Test Runner: Python script `verify_theme.py` (which uses tinycss2 or regex parsing to parse `stylesheet.css`, and `requests` / `urllib` to verify server status).
- Invocation: `python verify_theme.py`
- Pass/Fail Semantics: Exit code 0 if all assertions pass.
