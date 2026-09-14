import json


class _Layout:
    def __init__(self):
        self.template = None
        self.legend = None
        self.annotations = []


class Figure:
    def __init__(self, data=None, layout=None):
        self.data = list(data or [])
        self.layout = _Layout()

    def update_layout(self, **kwargs):
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
