# Original User Request

## Initial Request — 2026-06-24T19:11:32Z

# Teamwork Project Prompt — Draft

> Status: Launched

Overhaul the default Chainlit chat interface to fully implement the "Liquid Glass Frost" design aesthetic, matching the styling of the custom login pages. Ensure the UI is completely transformed without breaking any existing Chainlit functionality.

Working directory: E:\RAJ-WORK\PROJECT\nexus-ai
Integrity mode: demo

## Requirements

### R1. Theme Redesign
Strictly use `public/stylesheet.css` and `public/theme.json` to style existing Chainlit DOM elements. The chat background, sidebar, message bubbles, input box, and scrollbars must use the Liquid Glass Frost styling (cyan-violet gradients, deep frost backgrounds, glass blur effects). DO NOT inject custom React/JavaScript or modify `app.py` for this task.

### R2. Layout Overhaul
Fix layout overlaps, specifically where the sidebar overlaps the main chat area. Ensure the main content wrapper has the correct padding and z-index to prevent collisions, purely via CSS overrides.

## Verification Resources
The team must run a background agent (agent-as-judge) or programmatic script to parse the `public/stylesheet.css` and verify that structural overrides are present, and manually verify the UI by interacting with the Chainlit server on port 8000.

## Acceptance Criteria

### Verification Checks
- [ ] CSS parser or programmatic check confirms `public/stylesheet.css` overrides the `.MuiDrawer-paper` (or equivalent Chainlit sidebar class) with `backdrop-filter: blur(...)` and appropriate z-index/padding to prevent overlap.
- [ ] CSS parser confirms styles for `.message` or `.step` contain the cyan-violet gradient values.
- [ ] An agent-as-judge reviews the live UI on `http://localhost:8000` and confirms the sidebar no longer overlaps the chat interface.
- [ ] An agent-as-judge confirms the chat background contains the animated orb classes (`.orb`, `.grid`) injected correctly, or if not injectable via CSS, the dark frosted background is natively applied.
- [ ] Running `chainlit run app.py` throws zero frontend compilation or backend errors.
