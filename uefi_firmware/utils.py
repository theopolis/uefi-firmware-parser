# -*- coding: utf-8 -*-
import os
import re
import sys
import struct
import binascii
import functools
import threading
import zlib

nocolor = False

def blue(msg):
    '''Return the input string as console-escaped blue.'''
    if nocolor:
        return msg
    else:
        return "\033[1;36m%s\033[1;m" % msg


def red(msg):
    '''Return the input string as console-escaped red.'''
    if nocolor:
        return msg
    else:
        return "\033[31m%s\033[1;m" % msg


def green(msg):
    '''Return the input string as console-escaped green.'''
    if nocolor:
        return msg
    else:
        return "\033[32m%s\033[1;m" % msg


def purple(msg):
    '''Return the input string as console-escaped purple.'''
    if nocolor:
        return msg
    else:
        return "\033[1;35m%s\033[1;m" % msg


def print_error(msg):
    '''Write the input string to stderr.'''
    print(msg, file=sys.stderr)


def ascii_char(c):
    '''Return the ASCII or (.) representation of the input character.'''
    if isinstance(c, str):
        c = ord(c)
    if c >= 32 and c <= 126:
        return chr(c)
    return '.'


def hex_dump(data, size=16):
    '''Print a debug view of binary data similar to a hex editor

    Args:
        data (binary): Data to be printed.
        size (Optional[int]): Length of each line.
    '''
    def print_line(line):
        print("%s | %s" % (
            binascii.hexlify(line).decode(),
            "".join([ascii_char(c) for c in line])
        ))
        pass

    for i in range(0, len(data) // size):
        data_line = data[i * size:i * size + size]
        print_line(data_line)

    if not len(data) % size == 0:
        print_line(data[(len(data) % size) * -1:])


def sguid(b, big=False):
    '''RFC4122 binary GUID as string.'''
    if b is None or len(b) != 16:
        return ""
    a, b, c, d = struct.unpack("%sIHH8s" % (">" if big else "<"), b)
    d = ''.join('%02x' % c for c in bytes(d))
    return "%08x-%04x-%04x-%s-%s" % (a, b, c, d[:4], d[4:])


def s2aguid(s):
    '''RFC4122 string GUID as int array.'''
    guid = [s[:8], s[8 + 1:9 + 4], s[13 + 1:14 + 4],
            s[18 + 1:19 + 4] + s[-12:]]
    return aguid(b"".join([bytes.fromhex(part) for part in guid]), True)


def aguid(b, big=False):
    '''RFC4122 binary GUID as int array.'''
    if len(b) < 16:
        for i in range(16 - len(b)):
            b += b'\0'
    a, b, c, d = struct.unpack("%sIHH8s" % (">" if big else "<"), b)
    return [a, b, c] + [_c for _c in d]


def bit_set(field, bit):
    '''Check if bit is set (1) in field.'''
    return (field & bit == bit)


# Device names Windows reserves, with or without an extension.
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | \
    {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}


def safe_path_component(component):
    '''Return a filesystem-safe representation of a single path component.

    The same rules apply on every platform, so an image extracts to the same
    names everywhere.
    '''
    if isinstance(component, bytes):
        component = utf8_decode_safe(component)
    else:
        component = str(component)

    component = component.replace('\x00', '')
    # Path separators, the drive and stream separator, and the other
    # characters Windows does not allow in a name.
    component = re.sub(r'[/\\:*?"<>|\x01-\x1f\x7f]', '_', component)

    if component in ('', '.', '..'):
        return '_'
    # Windows drops trailing dots and spaces, so "a." would name "a".
    stripped = component.rstrip('. ')
    component = stripped + '_' * (len(component) - len(stripped))
    if component.split('.')[0].rstrip(' ').upper() in _RESERVED_NAMES:
        component = '_' + component
    return component


def safe_path(parent, *components):
    '''Join parent with sanitized path components.'''
    return os.path.join(
        parent, *[safe_path_component(part) for part in components])


def dump_data(name, data):
    '''Write binary data to name.

    Args:
        name (string): Path to output file, created if it does not exist.
        data (binary): Content to be written.
    '''
    try:
        if os.path.dirname(name) != '':
            if not os.path.exists(os.path.dirname(name)):
                os.makedirs(os.path.dirname(name))
        with open(name, 'wb') as fh:
            fh.write(data)
        print("Wrote: %s" % (red(name)))
    except Exception as e:
        print("Error: could not write (%s), (%s)." % (name, str(e)))


def is_erased(data):
    '''Check if data holds only erased flash, all 0xFF or all 0x00 bytes.'''
    return data.strip(b"\xff") == b"" or data.strip(b"\x00") == b""


# Volumes, sections and embedded images nest recursively, and compressed
# sections can expand far beyond their input. Both are bounded for each
# top-level parse so a crafted image fails cleanly instead of exhausting the
# stack or memory. Raise these if a real image needs more.
MAX_NESTING_DEPTH = 64
MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024

_parse_state = threading.local()


def limit_nesting(on_limit):
    '''Decorate a parse method that may recurse into nested objects.

    The outermost decorated call starts a new parse, which resets the
    decompression budget.

    Args:
        on_limit: The value to return instead of recursing past the limit.
    '''
    def decorator(method):
        @functools.wraps(method)
        def wrapper(*args, **kwargs):
            depth = getattr(_parse_state, "depth", 0)
            if depth >= MAX_NESTING_DEPTH:
                print_error("Error: objects are nested more than %d deep." % (
                    MAX_NESTING_DEPTH))
                return on_limit
            if depth == 0:
                _parse_state.decompressed = 0
            _parse_state.depth = depth + 1
            try:
                return method(*args, **kwargs)
            finally:
                _parse_state.depth = depth
        return wrapper
    return decorator


def reserve_decompression(size):
    '''Charge size bytes against the current parse's decompression budget.

    Return:
        bool: False, without charging, if size does not fit in the budget.
    '''
    used = getattr(_parse_state, "decompressed", 0)
    if used + size > MAX_DECOMPRESSED_BYTES:
        print_error("Error: decompressed data exceeds %d bytes." % (
            MAX_DECOMPRESSED_BYTES))
        return False
    _parse_state.decompressed = used + size
    return True


def zlib_decompress(data, wbits=zlib.MAX_WBITS):
    '''Decompress a zlib (or, with wbits, gzip) stream within the budget.

    Raises:
        zlib.error: The stream is invalid, truncated, or larger than the
            remaining decompression budget.
    '''
    remaining = MAX_DECOMPRESSED_BYTES - getattr(
        _parse_state, "decompressed", 0)
    decompressor = zlib.decompressobj(wbits)
    # A max_length of 0 means unlimited, so always allow at least one byte.
    output = decompressor.decompress(data, max(remaining, 0) + 1)
    if not decompressor.eof:
        raise zlib.error("truncated stream, or output over the budget")
    if not reserve_decompression(len(output)):
        raise zlib.error("output over the decompression budget")
    return output


def search_firmware_volumes(data, byte_align=16, limit=None, start=0):
    '''"Search a blob for '_FVH' magics, related to firmware volume headers.

    Args:
        start (Optional[int]): Search as if data began at this offset, without
            copying it. Returned offsets are relative to data.
    '''
    potential_volumes = []
    for aligned in range(start + 32, len(data), byte_align):
        if data[aligned:aligned + 4] == b'_FVH':
            potential_volumes.append(aligned)
            if limit and limit == len(potential_volumes):
                return potential_volumes
        magic = data[(aligned + byte_align // 2):(aligned + byte_align // 2 + 4)]
        if magic == b'_FVH':
            potential_volumes.append(aligned + byte_align // 2)
            if limit and limit == len(potential_volumes):
                return potential_volumes
    return potential_volumes


def flatten_firmware_objects(base_objects):
    '''Flatten the parent-child relations between firmware objects.

    It is often nice to remove the structured relationship between firmware
    objects. Each object maintains a pointer to its parent and will
    maintain pointers to children. The output will contain a flattened list
    of all children.

    Args:
        base_objects (list): Nested list of firmware objects.

    Returns:
        list: Non-Nested list of firmware objects.
    '''
    objects = []
    for _object in base_objects:
        objects.append(_object)
        if "objects" in _object and len(_object["objects"]) > 0:
            objects += flatten_firmware_objects(_object["objects"])
    return objects

def utf8_decode_safe(byte_array):
    '''Safely decode a byte array into a UTF-8 string.

    Args:
        byte_array (bytes): Unsafe (presumably) UTF-8 encoded string

    Returns:
        str: A proper string OR a 0x-prefixed hex representation of input byte array
    '''

    try:
        return byte_array.decode("utf-8")
    except UnicodeDecodeError:
        return "0x[{}]".format(byte_array.hex())
