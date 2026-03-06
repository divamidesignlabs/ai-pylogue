import html as html_lib
import json
import math
import re

from loguru import logger
from pylogue.embeds import store_html

THEME_TEXT = "#F1F1F1"
THEME_BG_GRADIENT = "linear-gradient(180deg, #303B57 0%, #0C121E 100%)"
COMPACT_NUMBER_FORMAT = ".2~s"
PERCENT_FORMAT = ".2%"


try:
    import pandas as pd
except ImportError:
    pd = None

# Pylogue custom color palette
PYLOGUE_COLORS = ["#8ACFF9", "#AD8AF9", "#768EF8", "#FF7F68", "#8FC187"]


def get_pylogue_color_palette(n_colors: int) -> list[str]:
    """Get Pylogue branded color palette.
    
    For n <= 5: returns the exact colors
    For n > 5: generates darker shades by cycling through base colors
    
    Args:
        n_colors: Number of colors needed
        
    Returns:
        List of hex color codes
    """
    if n_colors <= len(PYLOGUE_COLORS):
        return PYLOGUE_COLORS[:n_colors]

    colors = PYLOGUE_COLORS.copy()
    remaining = n_colors - len(PYLOGUE_COLORS)

    # Generate progressively darker shades in rounds to keep colors similar.
    for i in range(remaining):
        base_idx = i % len(PYLOGUE_COLORS)
        round_idx = (i // len(PYLOGUE_COLORS)) + 1
        base_color = PYLOGUE_COLORS[base_idx]
        rgb = tuple(int(base_color[j:j + 2], 16) for j in (1, 3, 5))
        factor = max(0.35, 1.0 - (0.18 * round_idx))
        shaded = tuple(max(0, min(255, int(c * factor))) for c in rgb)
        shade_hex = f"#{shaded[0]:02x}{shaded[1]:02x}{shaded[2]:02x}"
        colors.append(shade_hex)

    return colors

try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from plotly.utils import PlotlyJSONEncoder
except ImportError:
    px = None
    go = None
    make_subplots = None
    PlotlyJSONEncoder = None


def _preview(code: str, limit: int = 240) -> str:
    if not code:
        return ""
    compact = " ".join(code.strip().split())
    return compact[:limit] + ("..." if len(compact) > limit else "")


def _set_font_color(font_obj):
    if not isinstance(font_obj, dict):
        return
    font_obj["color"] = THEME_TEXT


def _set_title_color(title_obj):
    if isinstance(title_obj, str):
        return {"text": _humanize_field_name(title_obj), "font": {"color": THEME_TEXT}}
    if isinstance(title_obj, dict):
        if isinstance(title_obj.get("text"), str):
            title_obj["text"] = _humanize_field_name(title_obj["text"])
        title_obj.setdefault("font", {})
        _set_font_color(title_obj["font"])
        return title_obj
    return title_obj


def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _is_missing_value(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null", "nat"}:
        return True
    return False


def _replace_missing_with_unknown(values):
    if not isinstance(values, list):
        return values
    return ["Unknown" if _is_missing_value(v) else v for v in values]


def _replace_missing_in_customdata(customdata):
    if not isinstance(customdata, list):
        return customdata
    fixed = []
    for row in customdata:
        if isinstance(row, list):
            fixed.append(["Unknown" if _is_missing_value(cell) else cell for cell in row])
        else:
            fixed.append("Unknown" if _is_missing_value(row) else row)
    return fixed


def _normalize_trace_labels(trace: dict, trace_type: str):
    if not isinstance(trace, dict):
        return
    orientation = str(trace.get("orientation", "v")).lower()

    if trace_type in {"bar", "histogram", "waterfall", "funnel", "scatter", "scatter3d", "scattergeo", "scatterpolar", "scatterternary", "box", "violin"}:
        category_key = "y" if orientation == "h" else "x"
        if isinstance(trace.get(category_key), list):
            trace[category_key] = _replace_missing_with_unknown(trace[category_key])

    if trace_type in {"pie", "sunburst", "treemap", "icicle", "funnelarea"}:
        if isinstance(trace.get("labels"), list):
            trace["labels"] = _replace_missing_with_unknown(trace["labels"])
        if isinstance(trace.get("ids"), list):
            trace["ids"] = _replace_missing_with_unknown(trace["ids"])
        if isinstance(trace.get("parents"), list):
            trace["parents"] = _replace_missing_with_unknown(trace["parents"])

    if isinstance(trace.get("text"), list):
        trace["text"] = _replace_missing_with_unknown(trace["text"])

    if "customdata" in trace:
        trace["customdata"] = _replace_missing_in_customdata(trace.get("customdata"))


def _humanize_field_name(label: str) -> str:
    text = str(label or "").strip()
    if not text:
        return text
    lowered = text.lower()
    if lowered in {"expr0", "expr1", "expr2", "value", "values"}:
        return "Value"
    if "." in text:
        text = text.split(".")[-1]
    text = re.sub(r"__c$", "", text, flags=re.IGNORECASE)
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "Value"
    return text[:1].upper() + text[1:]


def _sanitize_hovertemplate(template: str) -> str:
    if not isinstance(template, str) or not template:
        return template

    # Remove technical metadata that should not appear in tooltips
    # marker.color in coloraxis contexts doesn't support formatting, so remove it entirely
    text = re.sub(r"%\{marker\.color(:[^}]*)?\}", "", template)
    
    # Remove other technical metadata that might leak into tooltips
    # Common patterns: trace[0], data[0], etc.
    text = re.sub(r"%\{trace\[[^]]+\]\.[^}]+\}", "", text)
    text = re.sub(r"%\{data\[[^]]+\]\.[^}]+\}", "", text)
    
    # Remove any label lines that are left with empty values after metadata removal
    # Matches labels followed by : or = with no placeholder value before <br>, <extra>, or end
    text = re.sub(r"(<br>|^)([^<>]+?)[:=]\s*(?=<br>|<extra>|$)", r"\1", text)
    
    # Humanize labels before ":" in segments like "<br>field_name: %{y}"
    def _colon_label(match):
        prefix = match.group(1)
        label = match.group(2)
        return f"{prefix}{_humanize_field_name(label)}: %{{"

    text = re.sub(r"(^|<br>)([^:<>{}%][^:<>{}%]*):\s*%\{", _colon_label, text)

    # Humanize labels before "=" in segments like "<br>expr0=%{y}"
    def _equals_label(match):
        prefix = match.group(1)
        label = match.group(2)
        return f"{prefix}{_humanize_field_name(label)}=%{{"

    text = re.sub(r"(^|<br>)([^=<>{}%][^=<>{}%]*)=%\{", _equals_label, text)

    # Ensure numeric placeholders use one centralized compact format (K/M/B).
    # Do not force-format %{x}: in many charts x is categorical text (e.g., owner name).
    text = re.sub(r"%\{(y|z|value)(:[^}]*)?\}", rf"%{{\1:{COMPACT_NUMBER_FORMAT}}}", text)
    # Ensure percentage placeholders use two decimals.
    text = re.sub(r"%\{percent(:[^}]*)?\}", rf"%{{percent:{PERCENT_FORMAT}}}", text)
    
    # Clean up any double <br> tags or trailing/leading <br> from metadata removal
    text = re.sub(r"(<br>\s*)+", "<br>", text)
    text = re.sub(r"^<br>|<br>$", "", text)
    
    return text


def _should_format_axis_as_numeric(traces: list, axis_key: str) -> bool:
    """Determine if an axis should use numeric formatting by checking trace data.
    
    Args:
        traces: List of trace dictionaries
        axis_key: Layout axis key (e.g., "xaxis", "xaxis2", "yaxis")
        
    Returns:
        True if axis should use numeric formatting, False for categorical/date axes
    """
    # Determine data key from axis key
    if axis_key.startswith("xaxis"):
        data_key = "x"
    elif axis_key.startswith("yaxis"):
        data_key = "y"
    else:
        return False  # Conservative default for unknown axes
    
    # Extract axis reference from layout key
    # "xaxis" → "x", "xaxis2" → "x2", "yaxis" → "y", "yaxis3" → "y3"
    if axis_key == f"{data_key}axis":
        axis_ref = data_key
    else:
        axis_ref = axis_key.replace(f"{data_key}axis", data_key)
    
    # Check traces that use this axis
    has_numeric_data = False
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        
        # Check if this trace uses this axis
        trace_axis_ref = trace.get(f"{data_key}axis", data_key)
        if trace_axis_ref != axis_ref:
            continue
        
        # Get the data
        data = trace.get(data_key)
        if isinstance(data, list) and len(data) > 0:
            # Check all non-null values to determine data type
            for val in data:
                if val is None or isinstance(val, dict):
                    continue
                # If ANY value is a string (category/date), don't format as numeric
                if isinstance(val, str):
                    return False
                # Track if we found numeric data
                if isinstance(val, (int, float)) and not math.isnan(val):
                    has_numeric_data = True
        
        # Also check if data is a dict (plotly sometimes wraps data)
        elif isinstance(data, dict):
            # Don't format complex data structures as numeric
            return False
    
    # Only apply numeric formatting if we confirmed numeric data exists
    return has_numeric_data


def _force_two_decimal_axis(axis: dict):
    if not isinstance(axis, dict):
        return
    axis["tickformat"] = COMPACT_NUMBER_FORMAT
    if isinstance(axis.get("hoverformat"), str) or "hoverformat" in axis:
        axis["hoverformat"] = COMPACT_NUMBER_FORMAT
    else:
        axis.setdefault("hoverformat", COMPACT_NUMBER_FORMAT)


def _improve_pie_representation(trace: dict):
    labels = trace.get("labels")
    values = trace.get("values")
    if not isinstance(labels, list) or not isinstance(values, list):
        return
    if len(labels) != len(values) or len(labels) == 0:
        return

    cleaned = []
    for lbl, val in zip(labels, values):
        num = _to_float(val)
        if num is None:
            continue
        cleaned.append((str(lbl), num))
    if not cleaned:
        return

    total = sum(v for _, v in cleaned)
    if total <= 0:
        return

    # Keep stronger categories and group tiny slices into "Other".
    cleaned.sort(key=lambda x: x[1], reverse=True)
    major = []
    other_sum = 0.0
    for i, (lbl, val) in enumerate(cleaned):
        pct = val / total
        if i < 6 and pct >= 0.03:
            major.append((lbl, val))
        else:
            other_sum += val
    if other_sum > 0:
        major.append(("Other", other_sum))

    trace["labels"] = [l for l, _ in major]
    trace["values"] = [v for _, v in major]
    trace["sort"] = True
    trace["direction"] = "clockwise"
    trace["textinfo"] = "none"
    trace["texttemplate"] = f"%{{percent:{PERCENT_FORMAT}}}"
    trace["textposition"] = "inside"
    trace["hovertemplate"] = (
        f"%{{label}}<br>%{{value:{COMPACT_NUMBER_FORMAT}}} "
        f"(%{{percent:{PERCENT_FORMAT}}})<extra></extra>"
    )


def _infer_value_label(trace_name: str = "") -> str:
    """Infer the appropriate label for tooltip values based on trace name.
    
    Args:
        trace_name: The name of the trace (e.g., "Critical Defect Count", "Total Cost (USD)")
        
    Returns:
        A contextually appropriate label (e.g., "Count", "Rate (%)", "Amount ($)")
    """
    name_lower = trace_name.lower()
    
    # Check for count/number indicators
    if any(word in name_lower for word in ["count", "number", "quantity", "total defect", "defects"]):
        return "Count"
    
    # Check for rate/percentage indicators
    if any(word in name_lower for word in ["rate", "percentage", "%", " pct", "ratio"]):
        return "Rate (%)"
    
    # Check for currency/cost indicators
    if any(word in name_lower for word in ["cost", "price", "revenue", "profit", "usd", "$", "amount", "sales", "expense"]):
        return "Amount ($)"
    
    # Check for volume indicators
    if any(word in name_lower for word in ["volume", "capacity", "size"]):
        return "Volume"
    
    # Check for time/duration indicators
    if any(word in name_lower for word in ["duration", "time", "hours", "minutes", "days"]):
        return "Duration"
    
    # Default fallback
    return "Value"


def _set_default_hovertemplate(trace: dict, trace_type: str, trace_count: int = 1):
    """Set default hovertemplate with trace name for multi-trace charts.
    
    Args:
        trace: The trace dict to modify
        trace_type: Type of trace (bar, scatter, etc.)
        trace_count: Total number of traces in the figure (for multi-series detection)
    """
    if trace.get("hovertemplate"):
        # Sanitize existing hovertemplate and add trace name if needed
        existing = _sanitize_hovertemplate(trace["hovertemplate"])
        # Add trace name for multi-trace charts if not already present
        if trace_count > 1 and "%{fullData.name}" not in existing and trace.get("name"):
            # Insert trace name at the beginning
            trace["hovertemplate"] = f"%{{fullData.name}}<br>{existing}"
        else:
            trace["hovertemplate"] = existing
        return
    
    # Infer appropriate value label from trace name
    trace_name = trace.get("name", "")
    value_label = _infer_value_label(trace_name)
    
    # Build hovertemplate with trace name for multi-trace charts
    trace_name_prefix = "%{fullData.name}<br>" if trace_count > 1 else ""
    
    if trace_type in {"heatmap", "contour", "histogram2d", "histogram2dcontour", "surface"}:
        trace["hovertemplate"] = (
            f"{trace_name_prefix}Category: %{{x}}<br>Series: %{{y}}<br>{value_label}: %{{z:{COMPACT_NUMBER_FORMAT}}}<extra></extra>"
        )
        return
    if trace_type in {"bar", "histogram", "waterfall", "funnel", "scatter", "scatter3d", "scattergeo", "scatterpolar", "scatterternary", "box", "violin"}:
        trace["hovertemplate"] = (
            f"{trace_name_prefix}Category: %{{x}}<br>{value_label}: %{{y:{COMPACT_NUMBER_FORMAT}}}<extra></extra>"
        )
        return


def _apply_plotly_theme(fig_json: dict):
    layout = fig_json.setdefault("layout", {})
    traces = fig_json.get("data", [])
    palette = get_pylogue_color_palette(max(5, len(traces)))

    layout["paper_bgcolor"] = "rgba(0,0,0,0)"
    layout["plot_bgcolor"] = "rgba(0,0,0,0)"
    # Force palette as default across Plotly traces unless explicitly overridden.
    layout["colorway"] = palette
    layout.setdefault("hoverlabel", {})
    layout["hoverlabel"]["bgcolor"] = "rgba(12,18,30,0.92)"
    layout["hoverlabel"]["bordercolor"] = "#3A475D"
    layout["hoverlabel"]["font"] = {"color": THEME_TEXT}
    layout.setdefault("margin", {})
    layout["margin"].setdefault("t", 84)
    layout["margin"].setdefault("r", 28)
    layout["margin"].setdefault("b", 64)
    layout["margin"].setdefault("l", 64)
    layout.setdefault("uniformtext", {})
    layout["uniformtext"].setdefault("mode", "hide")
    layout["uniformtext"].setdefault("minsize", 10)
    layout.setdefault("legend", {})
    layout["legend"].setdefault("bgcolor", "rgba(12,18,30,0.35)")
    layout["legend"].setdefault("bordercolor", "#3A475D")
    layout["legend"].setdefault("borderwidth", 1)

    layout.setdefault("font", {})
    _set_font_color(layout["font"])

    if "title" in layout:
        layout["title"] = _set_title_color(layout["title"])
    if isinstance(layout.get("legend"), dict):
        legend = layout["legend"]
        legend.setdefault("font", {})
        _set_font_color(legend["font"])
        if isinstance(legend.get("title"), dict):
            legend["title"].setdefault("font", {})
            _set_font_color(legend["title"]["font"])

    for key, axis in list(layout.items()):
        if not (key.startswith("xaxis") or key.startswith("yaxis")):
            continue
        if not isinstance(axis, dict):
            continue
        axis["color"] = THEME_TEXT
        axis.setdefault("tickfont", {})
        _set_font_color(axis["tickfont"])
        # Only apply numeric formatting to axes with numeric data
        if _should_format_axis_as_numeric(traces, key):
            _force_two_decimal_axis(axis)
        axis["automargin"] = True
        axis.setdefault("gridcolor", "rgba(58,71,93,0.45)")
        axis.setdefault("linecolor", "rgba(241,241,241,0.35)")
        axis.setdefault("zerolinecolor", "rgba(58,71,93,0.55)")
        if "title" in axis:
            axis["title"] = _set_title_color(axis["title"])

    if isinstance(layout.get("annotations"), list):
        for ann in layout["annotations"]:
            if not isinstance(ann, dict):
                continue
            ann.setdefault("font", {})
            _set_font_color(ann["font"])

    # Default continuous scale for heatmaps/contours.
    default_colorscale = []
    if len(palette) > 1:
        step = 1 / (len(palette) - 1)
        default_colorscale = [[idx * step, color] for idx, color in enumerate(palette)]
    elif palette:
        default_colorscale = [[0, palette[0]], [1, palette[0]]]

    # Plotly Express often uses shared coloraxis for color mapping.
    for key, value in list(layout.items()):
        if not key.startswith("coloraxis") or not isinstance(value, dict):
            continue
        if default_colorscale:
            value["colorscale"] = default_colorscale
        colorbar = value.get("colorbar")
        if isinstance(colorbar, dict):
            colorbar["tickformat"] = COMPACT_NUMBER_FORMAT
            colorbar.setdefault("tickfont", {})
            _set_font_color(colorbar["tickfont"])
            if "title" in colorbar:
                colorbar["title"] = _set_title_color(colorbar["title"])

    # Determine if we have grouped/stacked bars to avoid per-bar coloring
    barmode = layout.get("barmode", "")
    is_multi_trace_bar = barmode in {"group", "stack", "overlay", "relative"} or (
        len([t for t in traces if str(t.get("type", "")).lower() in {"bar", "histogram"}]) > 1
    )
    trace_count = len(traces)
    
    for idx, trace in enumerate(traces):
        if not isinstance(trace, dict):
            continue
        trace_type = str(trace.get("type", "")).lower()
        trace_color = palette[idx % len(palette)]
        _normalize_trace_labels(trace, trace_type)
        _set_default_hovertemplate(trace, trace_type, trace_count)

        marker = trace.get("marker")
        if not isinstance(marker, dict):
            marker = {}
            trace["marker"] = marker

        # Force discrete palette color on common trace styles.
        if trace_type in {
            "bar", "scatter", "box", "violin", "histogram", "funnel",
            "waterfall", "ohlc", "candlestick", "scatterpolar", "scattergeo",
            "scattermapbox", "scatterternary", "scatter3d", "barpolar",
            "cone", "streamtube", "choropleth", "choroplethmapbox"
        }:
            marker["color"] = trace_color
            if isinstance(trace.get("line"), dict):
                trace["line"]["color"] = trace_color
            if isinstance(marker.get("line"), dict):
                marker["line"]["color"] = trace_color
            if "fillcolor" in trace:
                trace["fillcolor"] = trace_color
            marker.setdefault("line", {})
            marker["line"].setdefault("width", 1)
            marker["line"].setdefault("color", "rgba(12,18,30,0.65)")

        if trace_type in {"scatter", "scatter3d", "scattergeo", "scatterpolar", "scatterternary"}:
            if str(trace.get("mode", "")).find("lines") >= 0:
                trace.setdefault("line", {})
                trace["line"].setdefault("width", 3)
                trace["line"].setdefault("shape", "spline")
            if str(trace.get("mode", "")).find("markers") >= 0:
                marker.setdefault("size", 8)
                marker.setdefault("opacity", 0.95)

        if trace_type in {"bar", "histogram", "waterfall", "funnel"}:
            trace.setdefault("opacity", 0.96)
            trace.setdefault("cliponaxis", False)
            # Only color individual bars when it's a single-trace chart
            # For grouped/stacked bars, keep the trace-level color to distinguish series
            if not is_multi_trace_bar:
                x_vals = trace.get("x")
                y_vals = trace.get("y")
                n_points = len(x_vals) if isinstance(x_vals, list) else (len(y_vals) if isinstance(y_vals, list) else 0)
                if n_points > 1:
                    marker["color"] = get_pylogue_color_palette(n_points)

        # Pie-family traces need per-slice colors.
        if trace_type in {"pie", "sunburst", "treemap", "icicle", "funnelarea"}:
            if trace_type == "pie":
                _improve_pie_representation(trace)
            if isinstance(trace.get("labels"), list):
                n_items = len(trace["labels"])
            elif isinstance(trace.get("ids"), list):
                n_items = len(trace["ids"])
            elif isinstance(trace.get("values"), list):
                n_items = len(trace["values"])
            elif isinstance(trace.get("x"), list):
                n_items = len(trace["x"])
            else:
                n_items = len(palette)
            marker["colors"] = get_pylogue_color_palette(max(1, n_items))

        # Force continuous palette scale for heatmap-like traces.
        if trace_type in {"heatmap", "contour", "histogram2d", "histogram2dcontour", "surface"}:
            if default_colorscale:
                trace["colorscale"] = default_colorscale
            if isinstance(marker, dict):
                marker["colorscale"] = default_colorscale

        if isinstance(trace.get("name"), str):
            trace.setdefault("textfont", {})
            _set_font_color(trace["textfont"])
        if isinstance(trace.get("colorbar"), dict):
            colorbar = trace["colorbar"]
            colorbar["tickformat"] = COMPACT_NUMBER_FORMAT
            colorbar.setdefault("tickfont", {})
            _set_font_color(colorbar["tickfont"])
            if "title" in colorbar:
                colorbar["title"] = _set_title_color(colorbar["title"])
        if isinstance(marker, dict) and isinstance(marker.get("colorbar"), dict):
            colorbar = marker["colorbar"]
            colorbar["tickformat"] = COMPACT_NUMBER_FORMAT
            colorbar.setdefault("tickfont", {})
            _set_font_color(colorbar["tickfont"])
            if "title" in colorbar:
                colorbar["title"] = _set_title_color(colorbar["title"])


def render_plotly_chart_dataframes(plotly_python: str, **dataframes):
    """Render a Plotly chart using Python code that defines `fig` with direct DataFrame inputs.
    
    This function is designed for applications that work with pre-loaded DataFrames,
    bypassing SQL query execution. Ideal for multi-dataset visualizations.
    
    Args:
        plotly_python: Python code that creates a `fig` variable using plotly
        **dataframes: Named DataFrames to pass into the execution context.
                     Common names: df, vdf, data_df, visual_df, etc.
    
    The code runs with access to:
    - All provided dataframes (e.g., df, vdf)
    - pd (pandas module)
    - px (plotly.express module)
    - go (plotly.graph_objects module)
    - make_subplots (plotly.subplots.make_subplots)
    - get_pylogue_colors (function to get pylogue color palette)
    - PYLOGUE_COLORS (pylogue color list)
    
    Returns:
        dict with _pylogue_html_id and message, or error details
    
    Example:
        render_plotly_chart_dataframes(
            plotly_python="fig = px.bar(df, x='category', y='value')",
            df=my_dataframe,
            vdf=visual_dataframe
        )
    """
    try:
        if (
            pd is None
            or go is None
            or px is None
            or make_subplots is None
            or PlotlyJSONEncoder is None
        ):
            return {
                "ok": False,
                "error": 'Missing dependencies. Install with: pip install "pylogue[dashboard]" plotly'
            }

        # Create execution environment with dataframes and pylogue utilities
        local_scope = {
            "pd": pd,
            "px": px,
            "go": go,
            "make_subplots": make_subplots,
            "get_pylogue_colors": get_pylogue_color_palette,
            "PYLOGUE_COLORS": PYLOGUE_COLORS,
        }
        
        # Add all provided dataframes to the execution context
        for name, dataframe in dataframes.items():
            if hasattr(dataframe, 'copy'):
                local_scope[name] = dataframe.copy()
            else:
                local_scope[name] = dataframe

        try:
            logger.info(
                f"Executing Plotly code with {len(dataframes)} dataframe(s): {list(dataframes.keys())}"
            )
            exec(plotly_python, local_scope)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Plotly code execution failed with dataframes: {}",
                list(dataframes.keys()),
            )
            return {"ok": False, "error": f"Error executing Plotly code: {exc}"}

        fig = local_scope.get("fig")
        if fig is None or not hasattr(fig, "to_plotly_json"):
            return {"ok": False, "error": "Plotly code must define a `fig` variable."}

        try:
            fig_json = fig.to_plotly_json()
            _apply_plotly_theme(fig_json)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Plotly serialization failed: fig_type={}",
                fig.__class__.__name__ if fig is not None else "unknown",
            )
            return {"ok": False, "error": f"Error serializing Plotly figure: {exc}"}

        layout = fig_json.get("layout") or {}
        user_height = layout.get("height")
        has_explicit_height = isinstance(user_height, (int, float))
        default_height = int(user_height) if has_explicit_height else 420

        if not has_explicit_height:
            fig_json.setdefault("layout", {})
            fig_json["layout"]["autosize"] = True
            fig_json["layout"].pop("width", None)

        fig_payload = json.dumps(fig_json, cls=PlotlyJSONEncoder)
        script_html = (
            "<div id='plot-wrap' style='width:100%;max-width:100%;margin:0;'>"
            "<div id='plot-root' style='width:100%;'></div>"
            "</div>"
            "<script src='https://cdn.plot.ly/plotly-2.35.2.min.js'></script>"
            "<script>"
            f"const fig={fig_payload};"
            f"const explicitHeight={'true' if has_explicit_height else 'false'};"
            f"const defaultHeight={default_height};"
            "const gd=document.getElementById('plot-root');"
            "function mobileHeight(){"
            "if(explicitHeight) return defaultHeight;"
            "const w=Math.max(280, Math.min(window.innerWidth||1024, 1400));"
            "return Math.max(280, Math.min(560, Math.round(w*0.6)));"
            "}"
            "function render(){"
            "fig.layout=fig.layout||{};"
            "fig.layout.autosize=true;"
            "fig.layout.width=null;"
            "fig.layout.height=mobileHeight();"
            "if(window.frameElement){"
            "window.frameElement.style.height=fig.layout.height+'px';"
            "window.frameElement.height=String(fig.layout.height);"
            "}"
            "Plotly.react(gd, fig.data||[], fig.layout, {responsive:true, displaylogo:false});"
            "}"
            "render();"
            "const ro=new ResizeObserver(()=>{"
            "render();"
            "try{Plotly.Plots.resize(gd);}catch(e){}"
            "});"
            "ro.observe(document.body);"
            "window.addEventListener('resize', ()=>{"
            "render();"
            "try{Plotly.Plots.resize(gd);}catch(e){}"
            "});"
            "</script>"
        )

        srcdoc = (
            "<!doctype html><html><head><meta charset='utf-8'/>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'/>"
            "<style>"
            "html,body{margin:0;padding:0;background:"
            f"{THEME_BG_GRADIENT};color:{THEME_TEXT};overflow:hidden;"
            "}"
            "</style>"
            "</head><body>"
            f"{script_html}"
            "</body></html>"
        )
        escaped_srcdoc = html_lib.escape(srcdoc, quote=True)
        iframe_html = (
            '<iframe '
            f'srcdoc="{escaped_srcdoc}" '
            f'height="{default_height}" '
            "style=\"width:100%;max-width:100%;height:"
            f"{default_height}px;border:0;display:block;\" "
            'title="Plotly Chart"></iframe>'
        )
        html_id = store_html(iframe_html)
        return {"_pylogue_html_id": html_id, "message": "Plotly chart rendered successfully."}
        
    except Exception as e:
        logger.exception(
            "Unhandled error in render_plotly_chart_dataframes with {} dataframe(s)",
            len(dataframes),
        )
        return {"ok": False, "error": f"Error in render_plotly_chart_dataframes: {e}"}


def render_plotly_chart_py(sql_query_runner: callable, sql_query: str, plotly_python: str):
    """Render a Plotly chart using Python code that defines `fig`.

    Prioritizes responsive behavior for chat UIs:
    - fills 100% available width of the chat card
    - adapts to browser resize and mobile breakpoints

    The code runs with access to:
    df (pandas DataFrame), pd (pandas), px (plotly.express),
    go (plotly.graph_objects), make_subplots (plotly.subplots.make_subplots).
    A list-of-dicts alias `data` is also provided for compatibility with
snippets that start with `pd.DataFrame(data)`.

    Plotly dropdown safety rules (prevents blank charts after selection):
    - For `updatemenus` with `method="update"`, always provide per-trace arrays:
      `x: [series.tolist()]`, `y: [series.tolist()]`, `text: [series.tolist()]`.
    - For `customdata`, pass a 2D payload wrapped per trace:
      `customdata: [df[[...]].to_numpy()]` (never a bare DataFrame).
    - Keep trace type stable across updates, e.g. `fig.update_traces(type="bar", ...)`.
    - Keep `hovertemplate` stable when using `customdata` in dropdown-driven updates.
    - Place dropdowns in a stable area (not over the title), for example:
      `updatemenus=[dict(buttons=buttons, x=0.01, y=1.02, xanchor="left", yanchor="bottom")]`
      and use `fig.update_layout(margin=dict(t=120))`.
      For placement below the chart, use `y=-0.12` and increase `margin.b`.
    - Pylogue auto-normalizes dropdown payloads for common update mistakes,
      so all agents get safer behavior by default.
    - Optional cross-trace click interaction contract (tool-level, agent-agnostic):
      put `layout.meta.pylogue_linked_interaction` with:
      `source_trace` (int), `target_trace` (int), `lookup` (dict),
      and optional `season_menu_index` (int), `default_season` (str),
      `target_title_annotation_index` (int).
      `lookup` keys can be `"<season>||<x_label>"` or `"<x_label>"`.
      Each payload can include `x`, `y`, `text`, `customdata`, `title`.
    """

    try:
        if (
            pd is None
            or go is None
            or px is None
            or make_subplots is None
            or PlotlyJSONEncoder is None
        ):
            return (
                'Missing dependencies. Install with: '
                'pip install "pylogue[dashboard]" plotly'
            )

        local_scope = {
            "pd": pd,
            "px": px,
            "go": go,
            "make_subplots": make_subplots,
            "get_pylogue_colors": get_pylogue_color_palette,
            "PYLOGUE_COLORS": PYLOGUE_COLORS,
        }
        if sql_query_runner is not None and sql_query is not None:
            df = pd.DataFrame(sql_query_runner(sql_query))
            local_scope["df"] = df
            local_scope["data"] = df.to_dict(orient="records")

        try:
            logger.info(
                f"Executed Plotly code: sql_attached={bool(sql_query_runner and sql_query)}, code_preview\n---\n{plotly_python}\n---\n"
            )
            exec(plotly_python, local_scope)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Plotly code execution failed: sql_attached={}, code_preview={!r}",
                bool(sql_query_runner and sql_query),
                _preview(plotly_python),
            )
            return f"Error executing Plotly code: {exc}"

        fig = local_scope.get("fig")
        if fig is None or not hasattr(fig, "to_plotly_json"):
            return "Error: Plotly code must define a `fig` variable."

        try:
            fig_json = fig.to_plotly_json()
            _apply_plotly_theme(fig_json)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Plotly serialization failed: fig_type={}, code_preview={!r}",
                fig.__class__.__name__ if fig is not None else "unknown",
                _preview(plotly_python),
            )
            return f"Error serializing Plotly figure: {exc}"

        layout = fig_json.get("layout") or {}
        user_height = layout.get("height")
        has_explicit_height = isinstance(user_height, (int, float))
        default_height = int(user_height) if has_explicit_height else 420

        if not has_explicit_height:
            # Let Plotly autosize width while we manage a mobile-friendly height.
            fig_json.setdefault("layout", {})
            fig_json["layout"]["autosize"] = True
            fig_json["layout"].pop("width", None)

        fig_payload = json.dumps(fig_json, cls=PlotlyJSONEncoder)
        script_html = (
            "<div id='plot-wrap' style='width:100%;max-width:100%;margin:0;'>"
            "<div id='plot-root' style='width:100%;'></div>"
            "</div>"
            "<script src='https://cdn.plot.ly/plotly-2.35.2.min.js'></script>"
            "<script>"
            f"const fig={fig_payload};"
            f"const explicitHeight={'true' if has_explicit_height else 'false'};"
            f"const defaultHeight={default_height};"
            "const gd=document.getElementById('plot-root');"
            "const TRACE_KEYS=['x','y','text','customdata'];"
            "function normalizePerTraceValue(value, traceCount){"
            "if(value===undefined||value===null) return value;"
            "if(!Array.isArray(value)) return [value];"
            "if(traceCount===1){"
            "if(value.length===0) return [[]];"
            "if(Array.isArray(value[0])) return value;"
            "return [value];"
            "}"
            "if(value.length===traceCount && value.every((item)=>Array.isArray(item)||item===null)) return value;"
            "if(!Array.isArray(value[0])) return [value];"
            "return value;"
            "}"
            "function stripFragileAnnotationKeys(obj){"
            "if(!obj||typeof obj!=='object') return;"
            "for(const key of Object.keys(obj)){"
            "if(key.startsWith('annotations[')&&key.endsWith('].text')) delete obj[key];"
            "}"
            "}"
            "function normalizeUpdateMenus(){"
            "const layout=fig.layout||{};"
            "const menus=layout.updatemenus||[];"
            "const traceCount=(fig.data||[]).length||1;"
            "for(const menu of menus){"
            "const buttons=(menu&&menu.buttons)||[];"
            "for(const btn of buttons){"
            "if(!btn||!Array.isArray(btn.args)||btn.args.length===0) continue;"
            "if(String(btn.method||'').toLowerCase()!=='update') continue;"
            "const dataArgs=btn.args[0];"
            "if(dataArgs&&typeof dataArgs==='object'){"
            "for(const key of TRACE_KEYS){"
            "if(key in dataArgs){"
            "dataArgs[key]=normalizePerTraceValue(dataArgs[key], traceCount);"
            "}"
            "}"
            "stripFragileAnnotationKeys(dataArgs);"
            "}"
            "const layoutArgs=btn.args.length>1?btn.args[1]:null;"
            "if(layoutArgs&&typeof layoutArgs==='object'){"
            "stripFragileAnnotationKeys(layoutArgs);"
            "}"
            "}"
            "}"
            "}"
            "function setupLinkedInteraction(){"
            "const meta=((fig.layout||{}).meta||{}).pylogue_linked_interaction;"
            "if(!meta||typeof meta!=='object') return;"
            "const sourceTrace=Number.isInteger(meta.source_trace)?meta.source_trace:0;"
            "const targetTrace=Number.isInteger(meta.target_trace)?meta.target_trace:1;"
            "const seasonMenuIndex=Number.isInteger(meta.season_menu_index)?meta.season_menu_index:0;"
            "const lookup=(meta.lookup&&typeof meta.lookup==='object')?meta.lookup:{};"
            "const defaultSeason=meta.default_season==null?'':String(meta.default_season);"
            "function normalizeLinkedSeries(value){"
            "if(Array.isArray(value) && value.length===1 && Array.isArray(value[0])){"
            "return value[0];"
            "}"
            "return value;"
            "}"
            "function activeSeason(){"
            "try{"
            "const menus=(gd.layout&&gd.layout.updatemenus)||[];"
            "const menu=menus[seasonMenuIndex];"
            "if(!menu||!Array.isArray(menu.buttons)) return defaultSeason;"
            "const active=Number.isInteger(menu.active)?menu.active:0;"
            "const btn=menu.buttons[active];"
            "if(!btn||btn.label==null) return defaultSeason;"
            "return String(btn.label);"
            "}catch(_err){return defaultSeason;}"
            "}"
            "gd.on('plotly_click', function(eventData){"
            "const point=eventData&&eventData.points&&eventData.points[0];"
            "if(!point||point.curveNumber!==sourceTrace) return;"
            "const label=String(point.x);"
            "const season=activeSeason();"
            "const combinedKey=season+'||'+label;"
            "const payload=lookup[combinedKey]||lookup[label];"
            "if(!payload||typeof payload!=='object') return;"
            "const update={};"
            "for(const key of TRACE_KEYS){"
            "if(payload[key]!==undefined){"
            "const val=(key==='customdata')?payload[key]:normalizeLinkedSeries(payload[key]);"
            "update[key]=[val];"
            "}"
            "}"
            "if(Object.keys(update).length===0) return;"
            "try{"
            "const fullData=gd._fullData||[];"
            "const target=fullData[targetTrace]||{};"
            "const yRef=String(target.yaxis||'y');"
            "const yLayoutKey=(yRef==='y')?'yaxis':'yaxis'+yRef.slice(1);"
            "const yVals=payload.y;"
            "if(Array.isArray(yVals) && yVals.length>0 && typeof yVals[0]==='string'){"
            "const patch={};"
            "patch[yLayoutKey+'.type']='category';"
            "Plotly.relayout(gd, patch);"
            "}"
            "}catch(_err){}"
            "Plotly.restyle(gd, update, [targetTrace]);"
            "if(payload.title){"
            "try{"
            "const anns=(gd.layout&&gd.layout.annotations)||[];"
            "const idx=Number.isInteger(meta.target_title_annotation_index)?meta.target_title_annotation_index:(anns.length>1?1:0);"
            "if(anns.length && idx>=0 && idx<anns.length){"
            "const relayoutPatch={};"
            "relayoutPatch['annotations['+idx+'].text']=String(payload.title);"
            "Plotly.relayout(gd, relayoutPatch);"
            "}else{"
            "Plotly.relayout(gd, {title:String(payload.title)});"
            "}"
            "}catch(_err){}"
            "}"
            "});"
            "}"
            "function mobileHeight(){"
            "if(explicitHeight) return defaultHeight;"
            "const w=Math.max(280, Math.min(window.innerWidth||1024, 1400));"
            "return Math.max(280, Math.min(560, Math.round(w*0.6)));"
            "}"
            "function render(){"
            "normalizeUpdateMenus();"
            "fig.layout=fig.layout||{};"
            "fig.layout.autosize=true;"
            "fig.layout.width=null;"
            "fig.layout.height=mobileHeight();"
            "if(window.frameElement){"
            "window.frameElement.style.height=fig.layout.height+'px';"
            "window.frameElement.height=String(fig.layout.height);"
            "}"
            "Plotly.react(gd, fig.data||[], fig.layout, {responsive:true, displaylogo:false});"
            "}"
            "render();"
            "setupLinkedInteraction();"
            "function debounce(func, wait) {"
            "let timeout;"
            "return function(...args) {"
            "clearTimeout(timeout);"
            "timeout = setTimeout(() => func.apply(this, args), wait);"
            "};"
            "}"
            "const debouncedRender = debounce(() => {"
            "render();"
            "try{Plotly.Plots.resize(gd);}catch(e){}"
            "}, 300);"
            "const ro=new ResizeObserver(debouncedRender);"
            "ro.observe(document.body);"
            "window.addEventListener('resize', debouncedRender);"
            "</script>"
        )

        srcdoc = (
            "<!doctype html><html><head><meta charset='utf-8'/>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'/>"
            "<style>"
            "html,body{margin:0;padding:0;background:"
            f"{THEME_BG_GRADIENT};color:{THEME_TEXT};overflow:hidden;"
            "}"
            # "#plot-wrap{"
            # "width:100%;max-width:100%;"
            # "border-radius:18px;"
            # "padding:8px;"
            # "box-shadow:0 0 24px rgba(138,207,249,0.32),0 0 56px rgba(173,138,249,0.24),inset 0 0 0 1px rgba(118,142,248,0.35);"
            # "animation:plotNeonPulse 2.6s ease-in-out infinite alternate;"
            # "}"
            # "#plot-root .svg-container,#plot-root .gl-container,#plot-root .main-svg{"
            # "filter:drop-shadow(0 0 8px rgba(138,207,249,0.25)) drop-shadow(0 0 18px rgba(118,142,248,0.2));"
            # "}"
            # "#plot-root .barlayer path,#plot-root .scatterlayer path,#plot-root .pielayer path,#plot-root .choroplethlayer path{"
            # "filter:drop-shadow(0 0 7px rgba(138,207,249,0.35));"
            # "}"
            # "@keyframes plotNeonPulse{"
            # "0%{box-shadow:0 0 16px rgba(138,207,249,0.24),0 0 36px rgba(173,138,249,0.18),inset 0 0 0 1px rgba(118,142,248,0.3);}"
            # "100%{box-shadow:0 0 28px rgba(138,207,249,0.42),0 0 72px rgba(173,138,249,0.32),inset 0 0 0 1px rgba(118,142,248,0.46);}"
            # "}"
            "</style>"
            "</head><body>"
            f"{script_html}"
            "</body></html>"
        )
        escaped_srcdoc = html_lib.escape(srcdoc, quote=True)
        iframe_html = (
            '<iframe '
            f'srcdoc="{escaped_srcdoc}" '
            f'height="{default_height}" '
            "style=\"width:100%;max-width:100%;height:"
            f"{default_height}px;border:0;display:block;\" "
            'title="Plotly Chart"></iframe>'
        )
        html_id = store_html(iframe_html)
        return {"_pylogue_html_id": html_id, "message": "Plotly chart rendered."}
    except Exception as e:
        logger.exception(
            "Unhandled error in render_plotly_chart_py: sql_attached={}, code_preview={!r}",
            bool(sql_query_runner and sql_query),
            _preview(plotly_python),
        )
        return f"Error in render_plotly_chart_py: {e}"
