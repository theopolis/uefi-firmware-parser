# -*- coding: utf-8 -*-

import argparse

from uefi_firmware.flash import *

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description= "Parse an Intel PCH/Flash descriptor.")
    parser.add_argument('-e', "--extract", action="store_true", help="Extract all sections.")
    parser.add_argument('-t', "--test", action="store_true", help="Test the parsing.")
    parser.add_argument("file", help="The file to work on")
    args = parser.parse_args()

    try:
        with open(args.file, 'rb') as fh: input_data = fh.read()
    except Exception, e:
        print "Error: Cannot read file (%s) (%s)." % (args.file, str(e))
        sys.exit(1)
    
    flash = FlashDescriptor(input_data)
    if not flash.valid_header:
        sys.exit(0)

    if args.test:
        print args.file

    flash.process()
    flash.showinfo()

    #if args.extract:
        #flash.dump("")
