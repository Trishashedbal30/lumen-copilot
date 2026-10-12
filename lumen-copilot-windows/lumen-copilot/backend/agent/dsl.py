"""
Action DSL: the only vocabulary the agent can use to touch the application.

Every action is a typed Pydantic model. The validator checks each one against the app metadata
(page exists, filter field exists on that page, value is a legal option, date within data range,
sort field is offered by the page) before anything executes.
"""
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class DateRange(BaseModel):
    start: str
    end: str
    label: str = ""
    preset: Optional[str] = None


class Sort(BaseModel):
    field: str
    dir: Literal["asc", "desc"] = "desc"


class UIState(BaseModel):
    page_id: str
    filters: Dict[str, List[str]] = Field(default_factory=dict)
    date_range: DateRange
    compare: Literal["none", "previous_period", "previous_year", "custom"] = "previous_period"
    compare_range: Optional[DateRange] = None
    sort: Optional[Sort] = None
    top_n: Optional[int] = None
    grain: Literal["auto", "day", "week", "month", "quarter"] = "auto"


class Navigate(BaseModel):
    type: Literal["navigate"] = "navigate"
    page_id: str


class SetFilter(BaseModel):
    type: Literal["set_filter"] = "set_filter"
    field: str
    values: List[str]


class ClearFilter(BaseModel):
    type: Literal["clear_filter"] = "clear_filter"
    field: str


class SetDateRange(BaseModel):
    type: Literal["set_date_range"] = "set_date_range"
    range: DateRange


class SetCompare(BaseModel):
    type: Literal["set_compare"] = "set_compare"
    mode: Literal["none", "previous_period", "previous_year", "custom"]
    range: Optional[DateRange] = None


class SetSort(BaseModel):
    type: Literal["set_sort"] = "set_sort"
    field: str
    dir: Literal["asc", "desc"] = "desc"


class SetTopN(BaseModel):
    type: Literal["set_top_n"] = "set_top_n"
    n: int


class SetGrain(BaseModel):
    type: Literal["set_grain"] = "set_grain"
    grain: Literal["auto", "day", "week", "month", "quarter"]


class Highlight(BaseModel):
    type: Literal["highlight"] = "highlight"
    widget_id: str


class ReadData(BaseModel):
    type: Literal["read_data"] = "read_data"
    view: str
    metric: str
    description: str = ""


class Analyze(BaseModel):
    type: Literal["analyze"] = "analyze"
    kind: Literal["kpi", "rank", "compare_periods", "compare_entities", "trend", "monthly_average", "drivers", "causes"]
    description: str = ""


class SaveView(BaseModel):
    type: Literal["save_view"] = "save_view"
    name: str


class Export(BaseModel):
    type: Literal["export"] = "export"
    widget_id: str


Action = Union[Navigate, SetFilter, ClearFilter, SetDateRange, SetCompare, SetSort, SetTopN, SetGrain,
               Highlight, ReadData, Analyze, SaveView, Export]

STATE_CHANGING = {"navigate", "set_filter", "clear_filter", "set_date_range", "set_compare", "set_sort", "set_top_n", "set_grain"}
NEEDS_CONFIRMATION = {"save_view"}  # persistent changes need a human yes; UI state changes are undoable


def describe_action(a, meta) -> str:
    t = a.type
    if t == "navigate":
        p = meta["pages"].get(a.page_id, {})
        return "Open " + " › ".join(p.get("breadcrumb", [a.page_id]))
    if t == "set_filter":
        return f"Set {a.field.replace('_', ' ')} = {', '.join(a.values)}"
    if t == "clear_filter":
        return f"Clear {a.field.replace('_', ' ')} filter"
    if t == "set_date_range":
        return f"Set date range: {a.range.label or (a.range.start + ' to ' + a.range.end)}"
    if t == "set_compare":
        if a.mode == "custom" and a.range:
            return f"Compare with {a.range.label}"
        return {"none": "Turn off comparison", "previous_period": "Compare with previous period",
                "previous_year": "Compare with same period last year"}.get(a.mode, a.mode)
    if t == "set_sort":
        return f"Sort by {a.field.replace('_', ' ')} ({'high → low' if a.dir == 'desc' else 'low → high'})"
    if t == "set_top_n":
        return f"Show top {a.n}"
    if t == "set_grain":
        return f"Group time by {a.grain}"
    if t == "highlight":
        return "Highlight the relevant widget"
    if t == "read_data":
        return a.description or f"Read {a.metric} from {a.view}"
    if t == "analyze":
        return a.description or f"Analyze ({a.kind})"
    if t == "save_view":
        return f"Save view “{a.name}”"
    if t == "export":
        return "Export grid as CSV"
    return t
