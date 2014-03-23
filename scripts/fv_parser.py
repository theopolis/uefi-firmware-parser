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

def _parse_firmware_capsule(data, name=0):
    print "Parsing FC at index (%s)." % hex(name)
    firmware_capsule = FirmwareCapsule(data, name)

    if not firmware_capsule.valid_header:
        return

    status= firmware_capsule.process()
    if args.test:
        print file_name, name, status
        return

    firmware_capsule.showinfo('')

    if args.extract:
        print "Dumping..."
        firmware_capsule.dump()

def _parse_firmware_volume(data, name=0):
    print "Parsing FV at index (%s)." % hex(name)
    firmware_volume = FirmwareVolume(data, name)

    if not firmware_volume.valid_header:
        return

    status= firmware_volume.process()
    if args.test:
        print file_name, name, status
        return

    firmware_volume.showinfo('')
    
    if args.extract:
        print "Dumping..."
        firmware_volume.dump()
    
    if args.generate is not None:
        print "Generating FDF..."
        firmware_volume.dump(args.generate)
        generator = uefi_generator.FirmwareVolumeGenerator(firmware_volume)

        dump_data(os.path.join(args.generate, "%s-%s.fdf" % (args.generate, name)), generator.output)
        #print generator.output
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
    parser.add_argument('-c', "--capsule", action="store_true", help='The input file is a firmware capsule, do not search.')
    parser.add_argument('-o', "--output", default=".", help="Dump EFI Files to this folder.")
    parser.add_argument('-e', "--extract", action="store_true", help="Extract all files/sections/volumes.")
    parser.add_argument('-g', "--generate", default= None, help= "Generate a FDF, implies extraction")
    parser.add_argument('-t', "--test", default=False, action= 'store_true', help= "Test file parsing, output name/success.")
    parser.add_argument("file", nargs='+', help="The file(s) to work on")
    args = parser.parse_args()
    
    for file_name in args.file:
        try:
            with open(file_name, 'rb') as fh: input_data = fh.read()
        except Exception, e:
            print "Error: Cannot read file (%s) (%s)." % (file_name, str(e))
            sys.exit(1)
        
        if args.capsule:
            _parse_firmware_capsule(input_data)
        elif args.firmware:
            _parse_firmware_volume(input_data) 
        else: 
            _brute_search(input_data)





