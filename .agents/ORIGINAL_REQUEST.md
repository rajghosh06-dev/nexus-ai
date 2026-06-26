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

## Follow-up — 2026-06-25T18:02:58+05:30

# Teamwork Project Prompt — Draft

> Status: Launched.
> Goal: Teamwork subagent is currently executing the project.

NexusAI is a Chainlit-based AI chat application. The goal is to perform a comprehensive overhaul of the UI, properly map and implement advanced Chat Profiles and Models, and build out major working functionalities referencing the official Chainlit documentation and cookbooks.

Working directory: `e:\RAJ-WORK\PROJECT\nexus-ai`
Integrity mode: demo

## Requirements

### R1. UI & Light Mode Polish
Resolve readability issues in Light Mode for buttons and other UI elements. Ensure the Liquid Glass Frost theme is applied consistently and beautifully across the entire application, including the Settings screen, to match the visual quality expected from a modern AI interface.

### R2. Core Chainlit Features Implementation
Implement and properly map the following core Chainlit features:
- **Chat Profiles**: Correctly set up `@cl.set_chat_profiles` (e.g., Omni, Gamer, Voice).
- **Chat Settings**: Properly configure `cl.ChatSettings` (Model selection, System Prompt) and update the UI accordingly.
- **User Sessions & History**: Ensure user sessions (`cl.user_session`) and chat history persistence are implemented properly and stably.
- **Authentication**: Ensure the existing authentication setup works seamlessly.

### R3. Advanced Interactive Features
Implement advanced conversational features based on the documentation:
- **Starters**: Set up conversation starters (`@cl.set_starters`).
- **Ask User**: Implement flows using `ask_for_input` (`cl.AskUserMessage`).
- **Actions**: Integrate interactive action buttons (`cl.Action`).
- **Multi-Modality**: Implement multi-modal features, referencing the `realtime-assistant` cookbook where applicable.

## Acceptance Criteria

### Verification Method: Agent-as-Judge
An independent agent will verify the implementation against the following criteria:

### UI & UX
- [ ] Light mode buttons and text have high contrast and are perfectly readable.
- [ ] The Settings screen is fully styled according to the Liquid Glass Frost theme (no default unstyled Chainlit UI).

### Functionality
- [ ] Chat Profiles are visible before starting a chat, and selecting different profiles changes the context/behavior.
- [ ] Chat Settings (Model, System Prompt) update correctly and the LLM routing respects these settings.
- [ ] Conversation starters appear on the welcome screen.
- [ ] A test action button can be triggered and handled by the backend.
- [ ] The `ask_for_input` prompt correctly pauses execution, receives user input, and resumes.
- [ ] Multi-modal input (e.g., audio/images) is accepted and processed by the system.
- [ ] Authentication successfully manages user identity and restricts access appropriately.
- [ ] Chat history is accurately persisted and restored between sessions.

