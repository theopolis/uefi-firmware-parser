# -*- coding: utf-8 -*-

import argparse

from uefi_firmware.flash import *

fd_magic = "\xFF" * 16 + "\x5A\xA5\xF0\x0F"

def search_flash_descriptor(data):
    indexes = []
    index = 0
    while True:
        index = data.find(fd_magic, index+1)
        if index < 0:
            break
        indexes.append(index)
    return indexes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description= "Parse an Intel PCH/Flash descriptor.")
    parser.add_argument('-e', "--extract", action="store_true", help="Extract all sections.")
    parser.add_argument('-t', "--test", action="store_true", help="Test the parsing.")
    parser.add_argument('-b', "--brute", action= "store_true", help= "Brute force search for flash descriptors")
    parser.add_argument("file", help="The file to work on")
    args = parser.parse_args()

    try:
        with open(args.file, 'rb') as fh: input_data = fh.read()
    except Exception, e:
        print "Error: Cannot read file (%s) (%s)." % (args.file, str(e))
        sys.exit(1)
    
    fds = []
    if args.brute:
        indexes = search_flash_descriptor(input_data)
        for i in indexes:
            fds.append(input_data[i:])
    else:
        fds.append(input_data)

    for descriptor in fds:
        flash = FlashDescriptor(descriptor)
        if not flash.valid_header:
            continue

        if args.test:
            print args.file

        flash.process()
        flash.showinfo()

    #if args.extract:
        #flash.dump("")
