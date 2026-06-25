import json
import re
import sys

def verify_theme():
    print("Verifying theme.json...")
    with open("public/theme.json", "r") as f:
        data = json.load(f)
    
    assert data["default"] == "dark", f"Expected default dark, got {data['default']}"
    dark = data["dark"]
    
    expected = {
        "background": "#070b14",
        "surface": "#0d1424",
        "paper": "#0e1526",
        "primary": "#00d4ff",
        "primaryForeground": "#070b14",
        "secondary": "#7c3aed",
        "text": "#ffffff",
        "textSecondary": "#94a3b8",
        "font": "Inter",
        "radius": "24px",
    }
    
    for k, v in expected.items():
        assert dark[k] == v, f"Expected dark[{k}] to be {v}, got {dark[k]}"
        
    assert dark["sidebar"]["background"] == "#080e1c", f"Expected dark.sidebar.background to be #080e1c, got {dark['sidebar']['background']}"
    print("theme.json verification PASSED!")

def verify_stylesheet():
    print("Verifying stylesheet.css...")
    with open("public/stylesheet.css", "r") as f:
        content = f.read()
        
    # a. Font import
    font_import = "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Orbitron:wght@500;700;900&display=swap');"
    assert font_import in content, "Orbitron font import not found or mismatch."
    
    # b. Root variables
    expected_vars = [
        "--nexus-cyan: #00d4ff;",
        "--nexus-violet: #7c3aed;",
        "--nexus-bg-dark: #070b14;",
        "--nexus-glass-bg: rgba(13, 20, 36, 0.6);",
        "--nexus-glass-border: rgba(0, 212, 255, 0.15);",
        "--nexus-text-primary: #ffffff;",
        "--nexus-text-secondary: #94a3b8;",
        "--nexus-radius: 24px;"
    ]
    for var in expected_vars:
        assert var in content, f"Expected CSS variable '{var}' not found in stylesheet.css"
        
    # c. Body pseudo-elements
    assert "body::before" in content, "body::before pseudo-element not found."
    assert "radial-gradient(ellipse at 15% 15%, rgba(0, 212, 255, 0.15) 0%, transparent 55%)" in content, "body::before radial-gradient 1 mismatch"
    assert "radial-gradient(ellipse at 85% 85%, rgba(124, 58, 237, 0.15) 0%, transparent 55%)" in content, "body::before radial-gradient 2 mismatch"
    assert "body::after" in content, "body::after pseudo-element not found."
    assert "transform: perspective(500px) rotateX(60deg) translateY(-10%) !important;" in content, "body::after transform mismatch"
    
    # d. Sidebar border leakage
    assert ".cl-sidebar .MuiDrawer-paper" in content, ".cl-sidebar .MuiDrawer-paper styling not found."
    assert "[class*=\"sidebar\"] .MuiDrawer-paper" in content, "[class*=\"sidebar\"] .MuiDrawer-paper styling not found."
    
    # Check that outer cl-sidebar is set to transparent/none
    outer_check = re.search(r'\[class\*="sidebar"\].*?\.cl-sidebar\s*\{\s*background:\s*transparent\s*!important;\s*border:\s*none\s*!important;\s*box-shadow:\s*none\s*!important;\s*\}', content, re.DOTALL)
    assert outer_check is not None, "Outer sidebar container transparency rules not found or mismatch."
    
    # e. Media query overrides and resets
    assert "@media (min-width: 900px)" in content, "Media query for screen widths >= 900px not found."
    assert "margin-left: 290px !important;" in content, "margin-left: 290px !important offset not found."
    assert "width: calc(100% - 290px) !important;" in content, "width override not found."
    assert "left: 290px !important;" in content, "left offset not found."
    assert "margin-left: 0 !important;" in content, "margin-left: 0 reset not found."
    assert "left: 0 !important;" in content, "left: 0 reset not found."
    assert "width: 100% !important;" in content, "width: 100% reset not found."
    
    # f. App title font family Orbitron
    app_title_check = re.search(r'\[class\*="app-name"\].*?font-family:\s*\'Orbitron\',\s*sans-serif\s*!important;', content, re.DOTALL)
    assert app_title_check is not None, "Orbitron font-family override for App title not found or mismatch."
    
    print("stylesheet.css verification PASSED!")

if __name__ == "__main__":
    try:
        verify_theme()
        verify_stylesheet()
        print("ALL VERIFICATIONS PASSED SUCCESSFULLY!")
        sys.exit(0)
    except AssertionError as e:
        print(f"VERIFICATION FAILED: {e}")
        sys.exit(1)
