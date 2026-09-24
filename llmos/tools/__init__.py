"""Tool registry. Each tool is a plain function taking (ctx, **args) and
returning a string (shown to the model) or raising ToolError. The JSON schema
the model is constrained by is generated from these declarations."""
import importlib
import inspect

REGISTRY = {}

# Permission classes (see docs/ARCHITECTURE.md 1.7)
R, C, D, E, N = "R", "C", "D", "E", "N"


class ToolError(Exception):
    pass


class Tool:
    def __init__(self, name, fn, doc, args, required, klass, hint):
        self.name, self.fn, self.doc = name, fn, doc
        self.args, self.required, self.klass, self.hint = args, required, klass, hint

    def classify(self, args):
        return self.klass(args) if callable(self.klass) else self.klass

    def schema(self):
        return {
            "type": "object",
            "properties": {
                "tool": {"const": self.name},
                "args": {"type": "object", "properties": self.args, "required": self.required,
                         "additionalProperties": False},
            },
            "required": ["tool", "args"],
        }

    def signature(self):
        parts = []
        for k, v in self.args.items():
            typ = v.get("type", "any")
            if "enum" in v:
                typ = "|".join(map(str, v["enum"]))
            parts.append(("%s:%s" % (k, typ)) + ("" if k in self.required else "?"))
        return "%s(%s)" % (self.name, ", ".join(parts))


def tool(name, doc, args=None, required=None, klass=R, hint=None):
    args = args or {}
    required = list(args) if required is None else required

    def deco(fn):
        REGISTRY[name] = Tool(name, fn, doc, args, required, klass, hint)
        return fn
    return deco


def s(desc=None, **kw):
    d = {"type": "string"}
    d.update(kw)
    return d


def i(**kw):
    d = {"type": "integer"}
    d.update(kw)
    return d


def b():
    return {"type": "boolean"}


def arr(items, **kw):
    d = {"type": "array", "items": items}
    d.update(kw)
    return d


def obj():
    return {"type": "object"}


MODULES = ("system", "memory", "web", "media", "files", "email", "schedule", "network", "models")


def load_all():
    for m in MODULES:
        importlib.import_module("llmos.tools." + m)
    return REGISTRY


def validate(name, args):
    """Light validation for calls that did not come through the grammar
    (fast paths, scheduled tasks)."""
    t = REGISTRY.get(name)
    if not t:
        raise ToolError("unknown tool %s" % name)
    if not isinstance(args, dict):
        raise ToolError("args must be an object")
    for r in t.required:
        if r not in args:
            raise ToolError("%s needs %s" % (name, r))
    for k in list(args):
        if k not in t.args:
            args.pop(k)
    return t


def run(ctx, name, args):
    t = validate(name, args)
    sig = inspect.signature(t.fn)
    kwargs = {k: v for k, v in args.items() if k in sig.parameters}
    out = t.fn(ctx, **kwargs)
    return "ok" if out is None else str(out)
