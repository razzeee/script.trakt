# -*- coding: utf-8 -*-

def deobfuscate(data):
    if not data or not isinstance(data, list):
        return ""
    return "".join(chr(b ^ 0x42) for b in data)

def obfuscate(data):
    if not data:
        return []
    return [ord(c) ^ 0x42 for c in data]
