#!/usr/bin/env python3
"""Check i18n.py language dicts: no duplicate keys, same key set as EN."""
import ast
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "src", "rootfs", "usr", "lib", "llmos", "llmos", "i18n.py")
LANGS = ["EN", "ZH", "ES", "FR", "DE", "JA"]

with open(PATH, encoding="utf-8") as f:
    tree = ast.parse(f.read(), filename=PATH)

dicts = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id in LANGS:
                dicts[t.id] = node.value

failed = False
for lang in LANGS:
    if lang not in dicts:
        print("FAIL missing dict %s" % lang)
        failed = True
        continue
    keys = [k.value for k in dicts[lang].keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    dups = sorted(k for k, n in Counter(keys).items() if n > 1)
    if dups:
        print("FAIL %s duplicate keys: %s" % (lang, ", ".join(dups)))
        failed = True
    else:
        print("ok %s no duplicate keys (%d keys)" % (lang, len(keys)))

if "EN" in dicts:
    en_keys = set(k.value for k in dicts["EN"].keys if isinstance(k, ast.Constant))
    for lang in LANGS[1:]:
        if lang not in dicts:
            continue
        ks = set(k.value for k in dicts[lang].keys if isinstance(k, ast.Constant))
        if ks != en_keys:
            print("FAIL %s key set differs from EN: missing=%s extra=%s" % (
                lang, sorted(en_keys - ks), sorted(ks - en_keys)))
            failed = True
        else:
            print("ok %s key set matches EN" % lang)

if failed:
    sys.exit(1)
print("all good")
