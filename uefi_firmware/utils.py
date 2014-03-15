# -*- coding: utf-8 -*-

import os
import struct

def blue(msg):
    return "\033[1;36m%s\033[1;m" % msg
def red(msg):
    return "\033[31m%s\033[1;m" % msg
def green(msg):
    return "\033[32m%s\033[1;m" % msg
def purple(msg):
    return "\033[1;35m%s\033[1;m" % msg

def ascii_char(c):
    if ord(c) >= 32 and ord(c) <= 126: return c
    return '.' 

def hex_dump(data, size= 16):	    
    def print_line(line):
        print "%s | %s" % (line.encode("hex"), "".join([ascii_char(c) for c in line]))
        pass

    for i in xrange(0, len(data)/size):
        data_line = data[i*size:i*size + size]
        print_line(data_line)
        
    if not len(data) % size == 0:
        print_line(data[(len(data) % size) * -1:])

def fguid(s):
    a, b, c, d, e = struct.unpack("<IHHH6s", s)
    return "%08x-%04x-%04x-%04x-%s" % (a,b,c,d,''.join('%02x'%ord(c) for c in e))

def rguid(s):
    a, b, c, d = struct.unpack("<IHH8s", s)
    return [a, b, c] + [ord(c) for c in d]
    pass

def dump_data(name, data):
    try:
        if os.path.dirname(name) is not '': 
            if not os.path.exists(os.path.dirname(name)):
                os.makedirs(os.path.dirname(name))
        with open(name, 'wb') as fh: fh.write(data)
        print "Wrote: %s" % (red(name))
    except Exception, e:
        print "Error: could not write (%s), (%s)." % (name, str(e))

def search_firmware_volumes(data, byte_align= 16):
    potential_volumes = []
    for aligned_start in xrange(32, len(data), byte_align):
        if data[aligned_start : aligned_start + 4] == '_FVH':
            potential_volumes.append(aligned_start)
        if data[aligned_start+byte_align/2 : aligned_start+byte_align/2+4] == '_FVH':
            potential_volumes.append(aligned_start+byte_align/2)
    return potential_volumes
    pass
