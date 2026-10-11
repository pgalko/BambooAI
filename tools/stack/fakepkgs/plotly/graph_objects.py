import json


class _Layout:
    def __init__(self):
        self.template = None
        self.legend = None
        self.annotations = []


class Figure:
    def __init__(self, data=None, layout=None):
        # one trace, or a list of them, as the real Figure takes (2026-10-10: go.Figure(go.Bar(...)) made a dict of a trace's keys)
        self.data = [data] if isinstance(data, dict) else list(data or [])
        self.layout = _Layout()

    def update_layout(self, **kwargs):
        for k, v in kwargs.items():             # the title and the axis titles, readable back as the real layout's are (2026-10-11)
            setattr(self.layout, k, v)
        return self

    def add_trace(self, trace):
        self.data.append(trace)
        return self

    def show(self, *args, **kwargs):
        import plotly.io as pio                 # the same route the real Figure.show takes
        return pio.show(self, *args, **kwargs)

    def to_json(self):
        return json.dumps({"data": [dict(t) for t in self.data], "layout": {"template": "plotly_dark"}})

    def write_json(self, filename):
        with open(filename, "w", encoding="utf-8") as fh:
            fh.write(self.to_json())


class _Trace(dict):
    kind = "scatter"

    def __init__(self, **kwargs):
        super().__init__(type=self.kind, **{k: (list(v) if hasattr(v, "__iter__") and not isinstance(v, str) else v) for k, v in kwargs.items()})


class Scatter(_Trace):
    kind = "scatter"


class Bar(_Trace):
    kind = "bar"
