## 2026-06-24T13:51:21Z

You are the Theme and Layout Worker for the Implementation Track (teamwork_preview_worker).
Your working directory is: E:\RAJ-WORK\PROJECT\nexus-ai\.agents\worker_m2_1
Your task:
1. Initialize your BRIEFING.md and progress.md.
2. Modify E:\RAJ-WORK\PROJECT\nexus-ai\public\theme.json to match the "Liquid Glass Frost" design parameters:
   - "background": "#070b14"
   - "surface": "#0d1424"
   - "paper": "#0e1526"
   - "primary": "#00d4ff"
   - "primaryForeground": "#070b14"
   - "secondary": "#7c3aed"
   - "text": "#ffffff"
   - "textSecondary": "#94a3b8"
   - "font": "Inter"
   - "radius": "1.5rem" (or "24px" to match index.html)
   - "sidebar": { "background": "#080e1c" }
3. Modify E:\RAJ-WORK\PROJECT\nexus-ai\public\stylesheet.css to implement the following changes:
   a. Update the Google Fonts import to include Orbitron:
      `@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Orbitron:wght@500;700;900&display=swap');`
   b. Map root CSS variables to "Liquid Glass Frost" values:
      `--nexus-cyan: #00d4ff;`
      `--nexus-violet: #7c3aed;`
      `--nexus-bg-dark: #070b14;`
      `--nexus-glass-bg: rgba(13, 20, 36, 0.6);`
      `--nexus-glass-border: rgba(0, 212, 255, 0.15);`
      `--nexus-text-primary: #ffffff;`
      `--nexus-text-secondary: #94a3b8;`
      `--nexus-radius: 24px;`
   c. Add body fixed pseudo-elements (`body::before` and `body::after`) to inject the floating blur orbs and the perspective grid without changing HTML markup:
      ```css
      body::before {
          content: '' !important;
          position: fixed !important;
          inset: 0 !important;
          z-index: -2 !important;
          background:
              radial-gradient(ellipse at 15% 15%, rgba(0, 212, 255, 0.15) 0%, transparent 55%),
              radial-gradient(ellipse at 85% 85%, rgba(124, 58, 237, 0.15) 0%, transparent 55%),
              #070b14 !important;
          pointer-events: none !important;
      }
      body::after {
          content: '' !important;
          position: fixed !important;
          inset: -50% !important;
          z-index: -1 !important;
          background-image: 
              linear-gradient(rgba(255, 255, 255, 0.015) 1px, transparent 1px),
              linear-gradient(90deg, rgba(255, 255, 255, 0.015) 1px, transparent 1px) !important;
          background-size: 50px 50px !important;
          transform: perspective(500px) rotateX(60deg) translateY(-10%) !important;
          opacity: 0.35 !important;
          pointer-events: none !important;
      }
      ```
   d. Fix border leakage from the collapsed sidebar:
      Instead of styling `[class*="sidebar"], .cl-sidebar` directly, apply the background, backdrop-filter, border-right, and box-shadow styles to `.cl-sidebar .MuiDrawer-paper` and `[class*="sidebar"] .MuiDrawer-paper`.
      Set `background: transparent !important`, `border: none !important`, and `box-shadow: none !important` on the outer `[class*="sidebar"], .cl-sidebar` containers.
   e. Fix layout overlaps by adding media query overrides for screen widths >= 900px to offset the main content elements:
      - Sibling `main` or `[class*="main"]` must have `margin-left: 290px !important; width: calc(100% - 290px) !important;` when the drawer is open.
      - Sibling `header` or `[class*="header"]` / `[class*="topbar"]` must have `left: 290px !important; width: calc(100% - 290px) !important;` when open.
      - The chat input area (`[data-testid="chat-input-wrapper"]`, bottom input/footer) inside `main` must have `left: 290px !important; width: calc(100% - 290px) !important;` when open.
      - Provide resets back to `margin-left: 0`, `left: 0`, and `width: 100%` when the sidebar is collapsed (e.g. drawer style has `width: 0` or `width: 0px`).
   f. Update the App title text font family to `Orbitron`:
      ```css
      [class*="app-name"],
      [class*="AppName"],
      [class*="title"] {
          font-family: 'Orbitron', sans-serif !important;
          font-weight: 700 !important;
          background: linear-gradient(135deg, #ffffff 0%, #a5b4fc 100%) !important;
          -webkit-background-clip: text !important;
          -webkit-text-fill-color: transparent !important;
          background-clip: text !important;
      }
      ```
4. Verify by checking if the changes compiled correctly, and report your results back via handoff.md and send a message.
