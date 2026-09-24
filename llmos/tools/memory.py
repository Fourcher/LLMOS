from . import tool, ToolError, s, R, C


@tool("remember", "Store a lasting preference or fact about the user. key is short (e.g. units, name, news_sources).",
      {"key": s(), "value": s()}, klass=C)
def remember(ctx, key, value):
    k = ctx.memory.set_pref(key, value)
    return "remembered %s: %s" % (k, value)


@tool("remember_fact", "Store a free-form fact worth recalling later (e.g. 'dentist is Dr Lee, Tuesdays').",
      {"text": s()}, klass=C)
def remember_fact(ctx, text):
    ctx.memory.add_fact(text)
    return "remembered"


@tool("forget", "Forget a stored preference (by key) or matching facts.", {"key": s()}, klass=C)
def forget(ctx, key):
    n = ctx.memory.forget(key)
    return "forgot %d item(s)" % n


@tool("recall", "Search stored facts, preferences and past conversations.", {"query": s()}, klass=R)
def recall(ctx, query):
    import time
    out = ["pref %s: %s" % kv for kv in ctx.memory.prefs() if any(w in (kv[0] + " " + kv[1]).lower() for w in query.lower().split())]
    out += ["fact: " + f for f in ctx.memory.search(query)]
    for ts, role, text in ctx.memory.search_transcript(query):
        out.append("%s %s: %s" % (time.strftime("%Y-%m-%d", time.localtime(float(ts))), role, text[:200]))
    return "\n".join(out) or "nothing found"
