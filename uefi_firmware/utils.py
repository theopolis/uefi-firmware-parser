# -*- coding: utf-8 -*-

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