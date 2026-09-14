"""
Synthesis Infographic Renderer
================================
Generates an SVG infographic from structured YAML.

This module is imported by BambooAI's main class. It has ONE public function:

    render_from_yaml_string(yaml_string: str) -> str
        Takes raw YAML text (from LLM extraction), returns SVG string.

Dependencies: pyyaml (already in bambooai requirements)
"""

import re
import yaml
import html as html_mod

try:
    from logger_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# STYLE CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════════

STYLE = {
    "bg":               "#FAFAFA",
    "dot_grid":         "#EDEDED",
    "spine_line":       "#CBD5CE",
    "node_fill":        "#5B8C6B",
    "node_border":      "#6E9E7E",
    "node_text":        "#FFFFFF",
    "connector":        "#C8D5CB",
    "arrow_fill":       "#9BB5A3",
    "title_bg":         "#E8F0EA",
    "title_text":       "#3A5A44",
    "subtitle_text":    "#7A9A84",
    "legend_bg":        "#F3F7F4",
    "legend_border":    "#DCE6DE",
    "phase_label":      "#3A5A44",
    "phase_summary":    "#7A9A84",
    "card_text":        "#2E2E2E",
    "card_detail":      "#8A8A8A",
    "conclusion_bg":    "#E2EDE5",
    "conclusion_text":  "#2E4A36",
    "conclusion_hl":    "#3A7A4A",
    "caveat_bg":        "#F5F5F5",
    "caveat_border":    "#E0E0E0",
    "caveat_text":      "#888888",

    "confirmed_border": "#5B8C6B",
    "confirmed_bg":     "#EFF6F1",
    "confirmed_icon_bg":"#5B8C6B",
    "confirmed_icon":   "✓",

    "tradeoff_border":  "#B89A6A",
    "tradeoff_bg":      "#F8F4ED",
    "tradeoff_icon_bg": "#B89A6A",
    "tradeoff_icon":    "⚠",

    "disproven_border": "#9A9A9A",
    "disproven_bg":     "#FAFAFA",
    "disproven_icon_bg":"#9A9A9A",
    "disproven_icon":   "✗",

    "font_body": "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif",
    "font_mono": "'SF Mono', 'Cascadia Code', 'Consolas', 'Liberation Mono', monospace",
}

# Layout constants
TITLE_H = 48
LEGEND_H = 32
BOTTOM_H = 80
BOTTOM_H_PER_CAVEAT = 14
SPINE_NODE_R = 24
CARD_PAD = 10
CARD_GAP = 8
CARD_LINE_H = 16
DETAIL_LINE_H = 13
COL_GAP = 16
CONNECTOR_H = 14
ARROW_W = 32
MARGIN_X = 32
MARGIN_TOP = 16
NODE_LABEL_GAP = 6


# ═════════════════════════════════════════════════════════════════════════════
# TEXT UTILITIES
# ═════════════════════════════════════════════════════════════════════════════

def _esc(text):
    return html_mod.escape(str(text), quote=True)


def _wrap_text(text, max_chars=32):
    words = text.split()
    lines, current = [], ""
    for w in words:
        if current and len(current) + 1 + len(w) > max_chars:
            lines.append(current)
            current = w
        else:
            current = f"{current} {w}" if current else w
    if current:
        lines.append(current)
    return lines


def _estimate_text_width(text, font_size):
    return len(text) * font_size * 0.55


# ═════════════════════════════════════════════════════════════════════════════
# SVG PRIMITIVES
# ═════════════════════════════════════════════════════════════════════════════

def _svg_rect(x, y, w, h, fill="#FFF", stroke="none", stroke_w=1, rx=0, opacity=1, dash=None):
    style = f'fill:{fill};stroke:{stroke};stroke-width:{stroke_w};opacity:{opacity};'
    if dash:
        style += f'stroke-dasharray:{dash};'
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" style="{style}"/>'


def _svg_line(x1, y1, x2, y2, color="#CCC", width=1.5, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"{d}/>'


def _svg_circle(cx, cy, r, fill="#444", stroke="none", stroke_w=1.5):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}"/>'


def _svg_text(x, y, text, size=12, color="#333", weight="normal", anchor="start", font=None, letter_spacing=None):
    f = font or STYLE["font_body"]
    ls = f' letter-spacing="{letter_spacing}px"' if letter_spacing else ""
    return (f'<text x="{x}" y="{y}" font-family="{f}" font-size="{size}" '
            f'fill="{color}" font-weight="{weight}" text-anchor="{anchor}"{ls}>'
            f'{_esc(text)}</text>')


def _svg_text_multiline(x, y, lines, size=12, color="#333", weight="normal", line_height=None, anchor="start", font=None):
    f = font or STYLE["font_body"]
    lh = line_height or (size + 4)
    spans = ""
    for i, line in enumerate(lines):
        dy = lh if i > 0 else 0
        spans += f'<tspan x="{x}" dy="{dy}">{_esc(line)}</tspan>'
    return (f'<text x="{x}" y="{y}" font-family="{f}" font-size="{size}" '
            f'fill="{color}" font-weight="{weight}" text-anchor="{anchor}">'
            f'{spans}</text>')


def _svg_arrow_right(x, y, width=32, color="#AAA"):
    head_size = 5
    shaft_end = x + width - head_size
    return (
        _svg_line(x, y, shaft_end, y, color=color, width=1.5) +
        f'<polygon points="{shaft_end},{y-head_size} {x+width},{y} {shaft_end},{y+head_size}" fill="{color}"/>'
    )


# ═════════════════════════════════════════════════════════════════════════════
# COMPONENT RENDERERS
# ═════════════════════════════════════════════════════════════════════════════

def _render_dot_grid(w, h, spacing=20, color="#E8E8E8"):
    return (
        f'<defs><pattern id="dotgrid" width="{spacing}" height="{spacing}" '
        f'patternUnits="userSpaceOnUse">'
        f'<circle cx="{spacing//2}" cy="{spacing//2}" r="0.5" fill="{color}"/>'
        f'</pattern></defs>'
        f'<rect width="{w}" height="{h}" fill="url(#dotgrid)" opacity="0.6"/>'
    )


def _render_title_bar(w, data):
    s = ""
    # Subtle accent line at top
    s += _svg_rect(0, 0, w, 3, fill="#5B8C6B")
    s += _svg_rect(0, 3, w, TITLE_H - 3, fill=STYLE["title_bg"])
    s += _svg_text(MARGIN_X, 30, data["title"], size=16, weight="600",
                   color=STYLE["title_text"], font=STYLE["font_mono"], letter_spacing=0.3)
    subtitle = data.get("subtitle", "")
    if subtitle:
        sw = _estimate_text_width(subtitle, 11)
        s += _svg_text(w - MARGIN_X - sw, 30, subtitle, size=11,
                       color=STYLE["subtitle_text"], font=STYLE["font_mono"])
    return s


def _render_legend_bar(w, y, legend):
    s = ""
    s += _svg_rect(0, y, w, LEGEND_H, fill=STYLE["legend_bg"], stroke=STYLE["legend_border"], stroke_w=0.5)
    s += _svg_line(0, y + LEGEND_H, w, y + LEGEND_H, color=STYLE["legend_border"], width=0.5)
    lx = MARGIN_X
    for key in ["confirmed", "tradeoff", "disproven"]:
        if key not in legend:
            continue
        icon = STYLE[f"{key}_icon"]
        icon_bg = STYLE[f"{key}_icon_bg"]
        label = legend[key]
        s += _svg_circle(lx + 8, y + LEGEND_H // 2, 8, fill=icon_bg)
        s += _svg_text(lx + 8, y + LEGEND_H // 2 + 4, icon, size=9, color="#FFF", weight="700", anchor="middle")
        s += _svg_text(lx + 20, y + LEGEND_H // 2 + 4, label, size=10, color="#666", font=STYLE["font_mono"])
        lx += 22 + _estimate_text_width(label, 10) + 24
    return s


def _compute_card_height(finding, max_chars):
    text_lines = _wrap_text(finding["text"], max_chars)
    detail_lines = _wrap_text(finding["detail"], max_chars + 4)
    h = CARD_PAD
    h += len(text_lines) * CARD_LINE_H
    h += 4
    h += len(detail_lines) * DETAIL_LINE_H
    h += CARD_PAD
    return h


def _render_finding_card(x, y, finding, card_w, max_chars):
    ftype = finding["type"]
    border_color = STYLE[f"{ftype}_border"]
    bg = STYLE[f"{ftype}_bg"]
    icon = STYLE[f"{ftype}_icon"]
    icon_bg = STYLE[f"{ftype}_icon_bg"]
    is_disproven = ftype == "disproven"

    text_lines = _wrap_text(finding["text"], max_chars)
    detail_lines = _wrap_text(finding["detail"], max_chars + 4)
    card_h = _compute_card_height(finding, max_chars)

    s = ""
    if is_disproven:
        s += _svg_rect(x, y, card_w, card_h, fill=STYLE["bg"], stroke=border_color, stroke_w=1, rx=4, dash="4,3")
    else:
        s += _svg_rect(x, y, card_w, card_h, fill=bg, stroke="#E0E0E0", stroke_w=0.5, rx=4)
        s += _svg_rect(x, y, 3, card_h, fill=border_color, rx=1)

    icon_cx = x + CARD_PAD + 10
    icon_cy = y + CARD_PAD + 8
    s += _svg_circle(icon_cx, icon_cy, 9, fill=icon_bg)
    s += _svg_text(icon_cx, icon_cy + 3.5, icon, size=9, color="#FFF", weight="700", anchor="middle")

    text_x = icon_cx + 16
    text_y = y + CARD_PAD + 12
    text_color = "#666" if is_disproven else STYLE["card_text"]
    s += _svg_text_multiline(text_x, text_y, text_lines, size=11.5, color=text_color, weight="500", line_height=CARD_LINE_H)

    detail_y = text_y + len(text_lines) * CARD_LINE_H + 2
    s += _svg_text_multiline(text_x, detail_y, detail_lines, size=9.5, color=STYLE["card_detail"], line_height=DETAIL_LINE_H)

    return s, card_h


def _render_bottom_bar(x, y, w, data, bar_h=80):
    s = ""
    caveats = data.get("caveats", [])
    conclusion = data.get("conclusion", "")

    s += _svg_line(x, y, x + w, y, color=STYLE["legend_border"], width=0.5)

    caveat_w = min(320, w * 0.25)
    s += _svg_rect(x, y, caveat_w, bar_h, fill=STYLE["caveat_bg"])
    s += _svg_line(x + caveat_w, y, x + caveat_w, y + bar_h, color=STYLE["caveat_border"], width=0.5)

    s += _svg_text(x + 14, y + 18, "⚑ CAVEATS", size=9, weight="600", color="#AAA", font=STYLE["font_mono"], letter_spacing=0.8)
    cy = y + 34
    for c in caveats[:4]:
        lines = _wrap_text(f"• {c}", int(caveat_w / 5.5))
        s += _svg_text_multiline(x + 14, cy, lines, size=9, color=STYLE["caveat_text"], line_height=12)
        cy += len(lines) * 12 + 2

    conc_x = x + caveat_w
    conc_w = w - caveat_w
    s += _svg_rect(conc_x, y, conc_w, bar_h, fill=STYLE["conclusion_bg"])
    s += _svg_text(conc_x + 16, y + bar_h // 2 + 4, "CONCLUSION", size=9, weight="600",
                   color="#7A9A84", font=STYLE["font_mono"], letter_spacing=0.8)

    label_end = conc_x + 100
    s += _svg_line(label_end, y + 16, label_end, y + bar_h - 16, color="#CBD5CE", width=0.5)

    conc_lines = _wrap_text(conclusion, int((conc_w - 130) / 6.5))
    s += _svg_text_multiline(label_end + 14, y + 22, conc_lines, size=12, color=STYLE["conclusion_text"], line_height=16)

    return s


# ═════════════════════════════════════════════════════════════════════════════
# MAIN LAYOUT ENGINE
# ═════════════════════════════════════════════════════════════════════════════

def _generate_svg(data):
    """Generate the complete SVG string from parsed data dict."""

    phases = data["phases"]
    findings = data["findings"]
    n_phases = len(phases)

    # Group findings by phase, split above/below
    phase_findings = {p["id"]: [] for p in phases}
    for f in findings:
        if f["phase"] in phase_findings:
            phase_findings[f["phase"]].append(f)

    phase_above = {}
    phase_below = {}
    for pid, pf in phase_findings.items():
        phase_above[pid] = [f for i, f in enumerate(pf) if i % 2 == 0]
        phase_below[pid] = [f for i, f in enumerate(pf) if i % 2 == 1]

    # Adaptive dimensions
    if n_phases <= 3:
        col_w, card_max_chars = 300, 38
    elif n_phases <= 5:
        col_w, card_max_chars = 250, 32
    elif n_phases <= 6:
        col_w, card_max_chars = 220, 28
    else:
        col_w, card_max_chars = 195, 24

    card_w = col_w - 16

    total_content_w = n_phases * col_w + (n_phases - 1) * (COL_GAP + ARROW_W)
    canvas_w = max(1200, MARGIN_X * 2 + total_content_w)

    # Measure max above/below heights
    max_above_h = max(60, max(
        (sum(_compute_card_height(f, card_max_chars) + CARD_GAP for f in phase_above[pid])
         for pid in phase_findings), default=0
    ))
    max_below_h = max(60, max(
        (sum(_compute_card_height(f, card_max_chars) + CARD_GAP for f in phase_below[pid])
         for pid in phase_findings), default=0
    ))

    # Bottom bar height
    caveats = data.get("caveats", [])
    caveat_w_est = min(320, canvas_w * 0.25)
    total_caveat_lines = sum(len(_wrap_text(f"• {c}", int(caveat_w_est / 5.5))) for c in caveats)
    bottom_h = max(BOTTOM_H, 36 + total_caveat_lines * BOTTOM_H_PER_CAVEAT)

    # Vertical layout
    header_h = TITLE_H + LEGEND_H
    node_label_h = 50
    spine_y = header_h + MARGIN_TOP + max_above_h + CONNECTOR_H + SPINE_NODE_R
    canvas_h = (header_h + MARGIN_TOP + max_above_h + CONNECTOR_H
                + SPINE_NODE_R * 2 + node_label_h
                + CONNECTOR_H + max_below_h + 20 + bottom_h)

    # Start SVG
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {canvas_w} {canvas_h}" '
        f'width="{canvas_w}" height="{canvas_h}" '
        f'font-family="{STYLE["font_body"]}">'
    ]

    # Background + dot grid
    parts.append(_svg_rect(0, 0, canvas_w, canvas_h, fill=STYLE["bg"]))
    parts.append(_render_dot_grid(canvas_w, canvas_h, spacing=20, color=STYLE["dot_grid"]))

    # Title + legend
    parts.append(_render_title_bar(canvas_w, data))
    legend = data.get("legend", {"confirmed": "Validated finding", "tradeoff": "Hidden cost / tradeoff", "disproven": "Hypothesis rejected"})
    parts.append(_render_legend_bar(canvas_w, TITLE_H, legend))

    # Column X positions
    start_x = (canvas_w - total_content_w) / 2
    col_centers = [start_x + i * (col_w + COL_GAP + ARROW_W) + col_w / 2 for i in range(n_phases)]

    # Spine line
    if len(col_centers) >= 2:
        parts.append(_svg_line(col_centers[0] - SPINE_NODE_R - 8, spine_y,
                               col_centers[-1] + SPINE_NODE_R + 8, spine_y,
                               color=STYLE["spine_line"], width=1.5))

    # Render each phase
    for i, phase in enumerate(phases):
        cx = col_centers[i]
        pid = phase["id"]
        card_x = cx - card_w / 2

        # Arrow to next
        if i < n_phases - 1:
            arrow_x = cx + col_w / 2 + COL_GAP / 2
            parts.append(_svg_arrow_right(arrow_x, spine_y, ARROW_W, STYLE["arrow_fill"]))

        # Findings ABOVE
        above_cards = phase_above[pid]
        if above_cards:
            card_y = spine_y - SPINE_NODE_R - CONNECTOR_H
            for f in reversed(above_cards):
                ch = _compute_card_height(f, card_max_chars)
                card_y -= ch
                svg_str, _ = _render_finding_card(card_x, card_y, f, card_w, card_max_chars)
                parts.append(svg_str)
                card_y -= CARD_GAP
            parts.append(_svg_line(cx, spine_y - SPINE_NODE_R - CONNECTOR_H, cx, spine_y - SPINE_NODE_R,
                                   color=STYLE["connector"], width=1))

        # Node
        parts.append(_svg_circle(cx, spine_y, SPINE_NODE_R, fill=STYLE["node_fill"],
                                 stroke=STYLE["node_border"], stroke_w=1.5))
        parts.append(_svg_text(cx, spine_y + 5, pid, size=13, color=STYLE["node_text"],
                               weight="600", anchor="middle", font=STYLE["font_mono"]))

        # Label + summary
        label_y = spine_y + SPINE_NODE_R + NODE_LABEL_GAP + 14
        parts.append(_svg_text(cx, label_y, phase["label"].upper(), size=10.5,
                               color=STYLE["phase_label"], weight="600", anchor="middle",
                               letter_spacing=0.4))
        summary_lines = _wrap_text(phase["summary"], int(col_w / 6))
        parts.append(_svg_text_multiline(cx, label_y + 14, summary_lines, size=9,
                                         color=STYLE["phase_summary"], line_height=12, anchor="middle"))

        # Findings BELOW
        below_cards = phase_below[pid]
        if below_cards:
            connector_bot = spine_y + SPINE_NODE_R + node_label_h
            parts.append(_svg_line(cx, connector_bot - 4, cx, connector_bot + CONNECTOR_H - 4,
                                   color=STYLE["connector"], width=1))
            card_y = connector_bot + CONNECTOR_H
            for f in below_cards:
                svg_str, ch = _render_finding_card(card_x, card_y, f, card_w, card_max_chars)
                parts.append(svg_str)
                card_y += ch + CARD_GAP

    # Bottom bar
    parts.append(_render_bottom_bar(0, canvas_h - bottom_h, canvas_w, data, bottom_h))

    parts.append('</svg>')
    return "\n".join(parts)


# ═════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ═════════════════════════════════════════════════════════════════════════════

def _validate(data):
    warnings = []
    if "title" not in data:
        warnings.append("MISSING: title")
    phases = data.get("phases", [])
    if len(phases) < 2:
        warnings.append(f"TOO FEW PHASES: {len(phases)}")
    findings = data.get("findings", [])
    valid_ids = {p["id"] for p in phases}
    for f in findings:
        if f.get("phase") not in valid_ids:
            warnings.append(f"BAD PHASE REF: '{f.get('phase')}'")
        if f.get("type") not in ("confirmed", "tradeoff", "disproven"):
            warnings.append(f"BAD TYPE: '{f.get('type')}'")
    return warnings


# ═════════════════════════════════════════════════════════════════════════════
# PUBLIC API — single entry point for BambooAI integration
# ═════════════════════════════════════════════════════════════════════════════

def _tidy_yaml(text):
    """The faults the models make when writing the infographic's YAML (2026-09-08): a key glued to
    its quoted value (tradeoff:"Cost...") and a doubled opening quote (disproven:""Ruled out").
    Both are mended line by line before parsing; anything else is left to the parser."""
    out = []
    for line in (text or "").splitlines():
        m = re.match(r'^(\s*(?:-\s*)?[A-Za-z_][\w ]*):(["\'])(.*)$', line)
        if m and not line.lstrip().startswith("#"):
            key, q, rest = m.group(1), m.group(2), m.group(3)
            if rest.startswith(q):
                rest = rest[1:]
            line = key + ": " + q + rest
        out.append(line)
    return "\n".join(out)


def render_from_yaml_string(yaml_string):
    """
    Convert a YAML string (from LLM extraction) into an SVG string.
    
    Args:
        yaml_string: Raw YAML text conforming to the infographic schema.
        
    Returns:
        SVG string ready for base64 encoding and frontend display.
        
    Raises:
        ValueError: If YAML parsing fails or critical fields are missing.
    """
    # Clean YAML: strip markdown fences if the LLM wrapped them
    cleaned = yaml_string.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```\w*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)
        cleaned = cleaned.strip()

    # Fix unquoted strings that contain colons (common LLM error)
    # Matches lines like '  title: Some Text: More Text' and wraps the value in quotes
    def _quote_unquoted_colons(line):
        m = re.match(r'^(\s+\w+):\s+(.+)$', line)
        if m and ':' in m.group(2) and not m.group(2).startswith('"') and not m.group(2).startswith("'"):
            return f'{m.group(1)}: "{m.group(2)}"'
        return line
    
    cleaned = '\n'.join(_quote_unquoted_colons(line) for line in cleaned.split('\n'))
    
    try:
        raw = yaml.safe_load(_tidy_yaml(cleaned))
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML: {e}")
    
    if raw is None:
        raise ValueError("YAML parsed to None — empty or malformed input")
    
    data = raw.get("infographic", raw)
    
    # Validate
    warnings = _validate(data)
    for w in warnings:
        logger.warning(f"Infographic schema warning: {w}")
    
    if "phases" not in data or not data["phases"]:
        raise ValueError("YAML missing required 'phases' field")
    if "findings" not in data or not data["findings"]:
        raise ValueError("YAML missing required 'findings' field")
    
    return _generate_svg(data)