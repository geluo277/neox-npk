"""Pure-Python MurmurHash3 x86 32-bit implementation.

Compatible with the subset of mmh3.hash(value, seed=0, signed=True) used by
NOTX UnZip. Strings are UTF-8 encoded; bytes-like inputs are hashed directly.
"""

def hash(key, seed=0, signed=True):
    if isinstance(key, str):
        data = key.encode('utf-8')
    elif isinstance(key, (bytes, bytearray, memoryview)):
        data = bytes(key)
    else:
        raise TypeError('key must be str or bytes-like')

    length = len(data)
    h = int(seed) & 0xFFFFFFFF
    c1 = 0xCC9E2D51
    c2 = 0x1B873593

    rounded_end = length & 0xFFFFFFFC
    for i in range(0, rounded_end, 4):
        k = data[i] | (data[i + 1] << 8) | (data[i + 2] << 16) | (data[i + 3] << 24)
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
        h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF

    tail = data[rounded_end:]
    k = 0
    if len(tail) == 3:
        k ^= tail[2] << 16
    if len(tail) >= 2:
        k ^= tail[1] << 8
    if len(tail) >= 1:
        k ^= tail[0]
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k

    h ^= length
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16

    if signed and h >= 0x80000000:
        return h - 0x100000000
    return h
