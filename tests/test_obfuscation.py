# -*- coding: utf-8 -*-
from resources.lib import obfuscation

def test_obfuscate():
    assert obfuscation.obfuscate("test") == [54, 39, 49, 54]

def test_deobfuscate():
    assert obfuscation.deobfuscate([54, 39, 49, 54]) == "test"

def test_obfuscate_empty():
    assert obfuscation.obfuscate("") == []

def test_deobfuscate_empty():
    assert obfuscation.deobfuscate("") == ""
    assert obfuscation.deobfuscate(None) == ""
    assert obfuscation.deobfuscate("not a list") == ""

def test_roundtrip():
    original = "Hello, World!"
    assert obfuscation.deobfuscate(obfuscation.obfuscate(original)) == original
