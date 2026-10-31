"""Tables and charts for a study page, drawn from the study's data/metrics.csv.

In a study's index.qmd:

    ```{python}
    from research_site import Study
    study = Study()
    study.bar_chart("F1", systems=["baseline", "new"])
    ```

A chart cell needs `#| renderings: [light, dark]`, since each chart outputs one figure per theme.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import yaml
from IPython.display import Markdown


class Theme:
    """Colors from the SIL Language Technology design system, matching theme-light.scss and theme-dark.scss.

    The light series are the brand hues; the dark ones are brand-derived steps that keep the
    validated lightness band and colorblind separation on the navy surface.
    """

    def __init__(self, name: str):
        dark = name == "dark"
        self.surface = "#0b1b2e" if dark else "#ffffff"
        self.text = "#e5eef8" if dark else "#333333"
        self.muted = "#a9bdd2" if dark else "#666666"
        self.grid = "#1f3a57" if dark else "#e0e0e0"
        light_series = ["#005cb9", "#ff6b00", "#93358d", "#00a7e1", "#509e2f"]
        dark_series = ["#337dc7", "#e8650a", "#a855a2", "#0a9cd3", "#509e2f"]
        self.series = dark_series if dark else light_series


class Study:
    def __init__(self, directory: str | Path = "."):
        self._metrics = pd.read_csv(Path(directory) / "data" / "metrics.csv")
        self._sources = yaml.safe_load((Path(directory) / "sources.yml").read_text(encoding="utf-8"))["sources"]

    def provenance(self) -> Markdown:
        """A sentence per source saying where the results came from, linked only where readers can follow."""
        lines = []
        for source in self._sources.values():
            if source.get("bucket"):
                digest = source["snapshot"].removeprefix("sha256:")
                lines.append(
                    f"- SIL's internal experiment store, snapshot `{digest[:12]}`. The results files, frozen at "
                    "publication, and the steps that produced them are kept there with the data, which isn't public."
                )
                continue
            repo = source["repo"].rstrip("/")
            name = repo.rsplit("/", 1)[-1]
            commit = source["commit"]
            if source["visibility"] == "public":
                lines.append(
                    f"- [{name}]({repo}) at commit [`{commit[:7]}`]({repo}/tree/{commit}). "
                    "Its results files are listed in [`sources.yml`](sources.yml)."
                )
            else:
                lines.append(
                    f"- {name}, an internal SIL repository, at commit `{commit[:7]}`. The results files and "
                    "the steps that produced them are kept there with the data, which isn't public."
                )
        return Markdown("\n".join(lines))

    def table(
        self,
        groups: list[str] | None = None,
        measures: list[str] | None = None,
        systems: list[str] | None = None,
        digits: int = 3,
        higher_is_better: bool = True,
        intervals: bool = True,
        measure_column: bool = True,
        average: bool = False,
        group_title: str = "Test",
    ) -> Markdown:
        """One row per (group, measure), one column per system; the best value in each row is bold.

        Set `measure_column=False` when the measure is named nearby, such as in the chart above.
        `average=True` adds a last row per measure with each system's mean over the groups, each
        group counting equally. `group_title` heads the first column.
        """
        rows = self._select(groups, measures, systems)
        systems = systems or list(dict.fromkeys(rows["system"]))
        lead = [group_title, "Measure"] if measure_column else [group_title]
        lines = [
            "| " + " | ".join(lead + systems) + " |",
            "|" + "---|" * len(lead) + "---:|" * len(systems),
        ]

        def add_row(group, measure, by_system, with_intervals, summary=False):
            values = by_system["value"].reindex(systems)
            best = values.max() if higher_is_better else values.min()
            formatted = []
            for system in systems:
                if pd.isna(values[system]):
                    formatted.append("—")
                    continue
                cell = by_system.loc[system]
                text = f"{cell['value']:.{digits}f}"
                if with_intervals and pd.notna(cell["lower"]):
                    text += f" ({cell['lower']:.{digits}f}–{cell['upper']:.{digits}f})"
                formatted.append(f"**{text}**" if values.count() > 1 and cell["value"] == best else text)
            lead = [group, measure] if measure_column else [group]
            # A summary row's label is bold, so the row stands apart while its values still mark the best.
            if summary:
                lead = [f"**{c}**" for c in lead]
            lines.append("| " + " | ".join(lead + formatted) + " |")

        for (group, measure), cells in rows.groupby(["group", "measure"], sort=False):
            add_row(group, measure, cells.set_index("system"), intervals)
        if average:
            for measure, cells in rows.groupby("measure", sort=False):
                means = cells.groupby("system")[["value"]].mean()
                add_row("Average", measure, means, with_intervals=False, summary=True)
        return Markdown("\n".join(lines))

    def dot_chart(
        self,
        measure: str,
        groups: list[str] | None = None,
        systems: list[str] | None = None,
        x_title: str | None = None,
        x_range: tuple[float, float] | None = None,
    ) -> None:
        """A dot per (group, system) with its interval as a whisker; for measures whose axis can't start at zero.

        Displays a light and a dark rendering.
        """
        self._show("dot", measure, groups, systems, x_title, x_range)

    def bar_chart(
        self,
        measure: str,
        groups: list[str] | None = None,
        systems: list[str] | None = None,
        x_title: str | None = None,
        x_range: tuple[float, float] | None = None,
    ) -> None:
        """Grouped horizontal bars from zero, one per (group, system), with intervals as whiskers.

        Displays a light and a dark rendering.
        """
        self._show("bar", measure, groups, systems, x_title, x_range)

    def _show(self, kind, measure, groups, systems, x_title, x_range) -> None:
        rows = self._select(groups, [measure], systems)
        systems = systems or list(dict.fromkeys(rows["system"]))
        for theme in (Theme("light"), Theme("dark")):
            self._figure(kind, rows, systems, theme, x_title or measure, x_range).show()

    def _figure(self, kind, rows, systems, theme: Theme, x_title, x_range) -> go.Figure:
        figure = go.Figure()
        # Reversed so the first group sits at the top, reading order matching the tables.
        categories = list(dict.fromkeys(rows["group"]))[::-1]
        # Grouped marks stack bottom-up in trace order, so add traces last-first (with the legend
        # reversed back) to put the first system on top, as the legend reads.
        for slot, system in reversed(list(enumerate(systems))):
            points = rows[rows["system"] == system]
            has_interval = points["lower"].notna()
            common = dict(
                x=points["value"],
                y=points["group"],
                name=system,
                orientation="h",
                error_x=dict(
                    type="data",
                    symmetric=False,
                    array=(points["upper"] - points["value"]).where(has_interval, 0),
                    arrayminus=(points["value"] - points["lower"]).where(has_interval, 0),
                    color=theme.text if kind == "bar" else theme.series[slot],
                    thickness=1.5 if kind == "bar" else 2,
                    width=0,
                ),
                customdata=points[["lower", "upper"]],
                hovertemplate=f"<b>{system}</b><br>%{{y}}<br>%{{x:.3f}}"
                + ("<br>95% interval %{customdata[0]:.3f}–%{customdata[1]:.3f}" if has_interval.any() else "")
                + "<extra></extra>",
            )
            if kind == "bar":
                figure.add_trace(go.Bar(**common, marker=dict(color=theme.series[slot], line=dict(width=0))))
            else:
                marker = dict(size=11, color=theme.series[slot], line=dict(width=2, color=theme.surface))
                figure.add_trace(go.Scatter(**common, mode="markers", marker=marker))
        # A 56px row with these gaps gives two bars of about 20px with a 2px gap between them.
        row_height = 56 if kind == "bar" else 44
        figure.update_layout(
            template="none",
            paper_bgcolor=theme.surface,
            plot_bgcolor=theme.surface,
            font=dict(color=theme.text, size=13, family="Source Sans 3, sans-serif"),
            height=90 + row_height * len(categories),
            margin=dict(l=10, r=10, t=10, b=50),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.0, x=0, traceorder="reversed", font=dict(color=theme.muted)
            ),
            hoverlabel=dict(bgcolor=theme.surface, font=dict(color=theme.text)),
            barmode="group",
            bargap=0.25,
            bargroupgap=0.1,
            barcornerradius=4,
            # Offsets dots for different systems along the category axis, so they don't hide each other.
            scattermode="group",
        )
        figure.update_xaxes(
            title=dict(text=x_title, font=dict(color=theme.muted)),
            gridcolor=theme.grid,
            zeroline=kind == "bar",
            zerolinecolor=theme.muted,
            zerolinewidth=1,
            rangemode="tozero" if kind == "bar" else "normal",
            range=x_range,
            tickfont=dict(color=theme.muted),
        )
        figure.update_yaxes(
            categoryorder="array", categoryarray=categories, automargin=True, showgrid=False, ticklabelstandoff=8
        )
        return figure

    def _select(self, groups, measures, systems) -> pd.DataFrame:
        rows = self._metrics
        for column, wanted in (("group", groups), ("measure", measures), ("system", systems)):
            if wanted is None:
                continue
            unknown = set(wanted) - set(rows[column])
            if unknown:
                raise KeyError(f"no {column} {sorted(unknown)} in metrics.csv")
            rows = rows[rows[column].isin(wanted)]
            rows = rows.assign(_order=rows[column].map({v: i for i, v in enumerate(wanted)}))
            rows = rows.sort_values("_order", kind="stable").drop(columns="_order")
        return rows
