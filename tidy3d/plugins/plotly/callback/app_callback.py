import urllib

from dash import callback, Output, Input, dcc, html

from tidy3d.plugins.plotly.simulation import SimulationPlotly
from tidy3d.plugins.plotly.data import DataPlotly
from tidy3d.plugins.plotly.store import get_store


@callback(
    Output("store", "data"),
    [Input("url", "search")],
)
def get_task_id(search):
    parsed = urllib.parse.urlparse(search)
    parsed_dict = urllib.parse.parse_qs(parsed.query)
    store = {}
    if parsed_dict.get("task_id"):
        store["task_id"] = parsed_dict.get("task_id")[0]
    return store


@callback(
    Output("container", "children"),
    [Input("store", "data")],
)
def display_simulation_data_app(store) -> dcc.Tabs:
    data_app = get_store().get_simulation_data(store)
    layout = dcc.Tabs([])
    component = SimulationPlotly(simulation=data_app.simulation).make_component()
    layout.children += [component]

    for monitor_name, monitor_data in data_app.monitor_data.items():
        data_plotly = DataPlotly.from_monitor_data(
            monitor_data=monitor_data, monitor_name=monitor_name
        )
        if data_plotly is None:
            continue
        component = data_plotly.make_component()
        layout.children += [component]

    layout.children += [dcc.Tab(
        [
            html.Div([html.H1("Solver Log")]),
            html.Div([html.Code(data_app.log, style={"whiteSpace": "pre-wrap"})]),
        ],
        label="log",
    )]
    return layout