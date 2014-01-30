# -*- coding: utf-8 -*-

import argparse

from uefi_firmware import *

def _brute_search(data):
    volumes = search_firmware_volumes(data)
    
    for index in volumes:
        _parse_firmware_volume(data[index-40:], name=index)
    pass

def _parse_firmware_volume(data, name="volume"):
    firmware_volume = FirmwareVolume(data, name)
    firmware_volume.process()
    firmware_volume.showinfo('')
    
    #print firmware_volume.iterate_objects(False)
    
    if args.extract:
        print "Dumping..."
        firmware_volume.dump()
    pass    
    pass

def _parse_firmware_filesystem(data):
    firmware_fs = FirmwareFileSystem(data)
    firmware_fs.process()
    
    print "Filesystem:"
    firmware_fs.showinfo(' ')
    
    if args.extract:
        print "Dumping..."
        firmware_fs.dump()
    pass

        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description= "Search a file for UEFI firmware volumes, parse and output.")
    parser.add_argument('-f', "--firmware", action="store_true", help='The input file is a firmware volume, do not search.')
    parser.add_argument('-o', "--output", default=".", help="Dump EFI Files to this folder.")
    parser.add_argument('-e', "--extract", action="store_true", help="Extract all files/sections/volumes.")
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





