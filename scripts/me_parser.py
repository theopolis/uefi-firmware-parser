# -*- coding: utf-8 -*-

import argparse

from uefi_firmware.me import *

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description= "Parse an Intel ME container's partitions and code modules.")
    parser.add_argument('-e', "--extract", action="store_true", help="Extract all modules/partitions.")
    parser.add_argument("file", help="The file to work on")
    args = parser.parse_args()

    try:
        with open(args.file, 'rb') as fh: input_data = fh.read()
    except Exception, e:
        print "Error: Cannot read file (%s) (%s)." % (args.file, str(e))
        sys.exit(1)

    #xtract = False
    #offset = 0
    #f = input_data

    #me_manifest = MeManifestHeader(input_data)
    #me_manifest.process()
    #me_manifest.showinfo()
    
    me_container = MeContainer(input_data)
    me_container.process()
    me_container.showinfo()

    if args.extract:
        me_container.dump("")
