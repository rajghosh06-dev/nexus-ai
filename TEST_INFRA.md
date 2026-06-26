# E2E Test Infra: NexusAI UI & Features Overhaul

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on implementation design.
- Methodology: Programmatic checks + API/UI checks + Automated verification scripts.

## Feature Inventory
| # | Feature | Source (requirement) | Tier 1 | Tier 2 | Tier 3 |
|---|---------|---------------------|:------:|:------:|:------:|
| 1 | UI Contrast & Settings Style | ORIGINAL_REQUEST R1 | 5 | 5 | ✓ |
| 2 | Chat Profiles (Omni, Gamer, Voice, Scholar) | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ |
| 3 | Chat Settings (Model, System Prompt, Temp, DeepSearch) | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ |
| 4 | User Sessions & History (Max 3 threads) | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ |
| 5 | Authentication (Passwordless verification) | ORIGINAL_REQUEST R2 | 5 | 5 | ✓ |
| 6 | Conversation Starters | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ |
| 7 | Ask User Flow (AskUserMessage) | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ |
| 8 | Interactive Actions (cl.Action) | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ |
| 9 | Multi-Modality Inputs | ORIGINAL_REQUEST R3 | 5 | 5 | ✓ |

## Test Architecture
- Test Runner: Python test suite (e.g. `verify_features.py`) invoking Chainlit server in a background process, and making programmatic HTTP requests / DB assertions / page queries.
- Directory layout: tests should be placed in `tests/` or structured inside a verification script.
- Pass/Fail Semantics: Exit code 0 if all assertions pass.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | End-to-End User Session | Auth, Profiles, Starters, Settings, History | High |
| 2 | Gamer Profile & Action flow | Profiles, Ask User, Actions, Chat Settings | High |
| 3 | Scholar Profile & Search | Profiles, History, Starters | Medium |
| 4 | Multi-modal Voice/Image thread | Profiles, Multi-modality, Settings | High |
| 5 | Session restoration & limits | Auth, Sessions, History, Thread limit | High |

## Coverage Thresholds
- Tier 1: 45 test assertions (5 per feature)
- Tier 2: 45 test assertions (5 boundary/corner cases per feature)
- Tier 3: 9 cross-feature interaction assertions
- Tier 4: 5 realistic application scenarios
