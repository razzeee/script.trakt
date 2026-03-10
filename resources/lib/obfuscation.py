# -*- coding: utf-8 -*-
from typing import List, Union


def deobfuscate(data: Union[List[int], str]) -> str:
    if not data or not isinstance(data, list):
        return ""
    return "".join(chr(b ^ 0x42) for b in data)

def obfuscate(data: str) -> List[int]:
    if not data:
        return []
    return [ord(c) ^ 0x42 for c in data]
