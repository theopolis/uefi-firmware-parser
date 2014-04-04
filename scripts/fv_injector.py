# -*- coding: utf-8 -*-

import argparse
import os

from uefi_firmware.uefi import *
from uefi_firmware.generator import uefi as uefi_generator
from uefi_firmware.utils import dump_data

from uefi_firmware.pfs import PFSFile

def brute_search(data):
    volumes = search_firmware_volumes(data)
    
    for index in volumes:
        _parse_firmware_volume(data[index-40:], name=index-40)
    pass

def parse_pfs(data):
    pfs = PFSFile(data)
    if not pfs.check_header():
        print "Error: Cannot parse file (%s) as a Dell PFS." % args.file
    pfs.process()

    data = pfs.build()
    dump_data("injected", data)    
    pass

def parse_firmware_volume(data, name="volume"):
    print "Parsing FV at index (%s)." % name
    firmware_volume = FirmwareVolume(data, name)

    if not firmware_volume.valid_header:
        return

    firmware_volume.process()
    data = firmware_volume.build()
    dump_data("injected", data)
    #firmware_volume.showinfo('')
    pass

        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description= "Search a file for UEFI firmware volumes, parse and output.")
    parser.add_argument('-f', "--firmware", action="store_true", help='The input file is a firmware volume.')
    parser.add_argument('-b', "--brute", action="store_true", help= 'The input is a blob and may contain FV headers.')
    parser.add_argument('-c', "--capsule", action="store_true", help='The input file is a firmware capsule.')
    parser.add_argument('-p', "--pfs", action="store_true", help='The input file is a Dell PFS.')
    
    parser.add_argument("file", help="The file to work on")
    args = parser.parse_args()
    
    try:
        with open(args.file, 'rb') as fh: input_data = fh.read()
    except Exception, e:
        print "Error: Cannot read file (%s) (%s)." % (args.file, str(e))
        sys.exit(1)
        
    if args.brute:
        brute_search(input_data)
    elif args.capsule:
        pass
    elif args.pfs:
        parse_pfs(input_data)
    else:
        parse_firmware_volume(input_data) 


