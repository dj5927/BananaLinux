#!/usr/bin/env python3
"""Check translation coverage and preservation of runtime format fields."""
from pathlib import Path
from collections import Counter
import re
import unicodedata

root = Path(__file__).resolve().parents[1]
directory = root / "ui/assets/lang"
fields = re.compile(r"\{[^{}]*\}|%(?:%|[-+#0]*\d*(?:\.\d+)?[hljztL]*[diuoxXfFeEgGaAcspn]|[HM])")

def read(path):
    result = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        p, context, source, translation = line.split("\t", 3)
        key = (p, context, source)
        if path.stem == "ko":
            assert key not in result, (path, n, "duplicate")
            assert translation.strip(), (path, n, "empty translation")
            assert unicodedata.is_normalized("NFC", translation), (path, n, "non-NFC")
            assert Counter(fields.findall(source)) == Counter(fields.findall(translation)), (path, n, source)
        result[key] = translation
    return result

ko = read(directory / "ko.tsv")
expected = set()
for code in ("es", "fi", "it", "ru", "zh-cn"):
    expected.update(read(directory / (code + ".tsv")))
assert not expected - ko.keys(), f"Missing translations: {expected - ko.keys()}"
print(f"Korean: {len(ko)} entries, {len(expected)} reference entries, format fields preserved")
