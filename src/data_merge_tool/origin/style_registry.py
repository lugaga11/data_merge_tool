from __future__ import annotations

STYLE_FIELDS: frozenset[str] = frozenset(
    {
        "page.size_in",
        "page.anti_alias",
        "layer.geometry_in",
        "layer.frame",
        "layer.line_width_pt",
        "layer.scale_elements",
        "axis.x_scale",
        "axis.y_scale",
        "axis.grid",
        "plot.line_width_pt",
        "plot.symbol_size_pt",
        "text.x_title",
        "text.y_title",
        "text.legend_text",
        "text.title_size_pt",
        "text.tick_size_pt",
        "text.legend_size_pt",
        "legend.visibility",
        "legend.frame",
        "legend.position",
    }
)


def filter_known_style_paths(paths: object) -> list[str]:
    if not isinstance(paths, list):
        return []
    return sorted(str(path) for path in paths if str(path) in STYLE_FIELDS)
