# -*- coding: utf-8 -*-

import argparse
import os

from uefi_firmware.uefi import *
from uefi_firmware.generator import uefi as uefi_generator
from uefi_firmware.utils import dump_data

def _brute_search(data):
    volumes = search_firmware_volumes(data)
    
    for index in volumes:
        _parse_firmware_volume(data[index-40:], name=index-40)
    pass

def _parse_firmware_volume(data, name="volume"):
    print "Parsing FV at index (%s)." % hex(name)
    firmware_volume = FirmwareVolume(data, name)

    if not firmware_volume.valid_header:
        return

    firmware_volume.process()
    data = firmware_volume.build()
    #firmware_volume.showinfo('')
    
    pass

def _parse_firmware_filesystem(data):
    firmware_fs = FirmwareFileSystem(data)
    firmware_fs.process()
    
    #print "Filesystem:"
    #firmware_fs.showinfo(' ')
    
    pass
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description= "Search a file for UEFI firmware volumes, parse and output.")
    parser.add_argument('-f', "--firmware", action="store_true", help='The input file is a firmware volume, do not search.')
    parser.add_argument("file", help="The file to work on")
    args = parser.parse_args()
    
    try:
        with open(args.file, 'rb') as fh: input_data = fh.read()
    except Exception, e:
        print "Error: Cannot read file (%s) (%s)." % (args.file, str(e))
        sys.exit(1)
        
    if args.firmware:
        _parse_firmware_volume(input_data) 
    else: 
        _brute_search(input_data)





