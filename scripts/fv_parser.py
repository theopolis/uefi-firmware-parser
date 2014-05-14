# -*- coding: utf-8 -*-

import argparse
import os

from uefi_firmware.uefi import *
from uefi_firmware.utils import *
from uefi_firmware.flash import FlashDescriptor
from uefi_firmware.me import MeContainer
from uefi_firmware.pfs import PFSFile
from uefi_firmware.generator import uefi as uefi_generator

def _process_show_extract(parsed_object):
    parsed_object.process()
    if not args.quiet:
        parsed_object.showinfo('')

    if args.extract:
        print "Dumping..."
        parsed_object.dump(args.output)

def brute_search_volumes(data):
    volumes = search_firmware_volumes(data)
    for index in volumes:
        parse_firmware_volume(data[index-40:], name=index-40)
    pass

def brute_search_flash(data):
    descriptors = search_flash_descriptor(data)
    for index in descriptors:
        parse_flash_descriptor(data[index:])
    pass

def parse_firmware_capsule(data, name=0):
    print "Parsing FC at index (%s)." % hex(name)
    firmware_capsule = FirmwareCapsule(data, name)
    if not firmware_capsule.valid_header:
        return
    _process_show_extract(firmware_capsule)

def parse_file(data, name=""):
    print "Parsing Firmware File"
    firmware_file = FirmwareFile(data)
    _process_show_extract(firmware_file)

def parse_flash_descriptor(data):
    print "Parsing Flash descriptor."
    flash = FlashDescriptor(data)
    if not flash.valid_header:
        return
    _process_show_extract(flash)

def parse_me(data):
    print "Parsing Intel ME"
    me = MeContainer(data)
    _process_show_extract(me)

def parse_pfs(data):
    print "Parsing Dell PFS.HDR update"
    pfs = PFSFile(data)
    if not pfs.check_header():
        return
    _process_show_extract(pfs)

def parse_firmware_volume(data, name=0):
    print "Parsing FV at index (%s)." % hex(name)
    firmware_volume = FirmwareVolume(data, name)
    if not firmware_volume.valid_header:
        return
    _process_show_extract(firmware_volume)
    
    if args.generate is not None:
        print "Generating FDF..."
        firmware_volume.dump(args.generate)
        generator = uefi_generator.FirmwareVolumeGenerator(firmware_volume)
        dump_data(os.path.join(args.generate, "%s-%s.fdf" % (args.generate, name)), generator.output)
    pass
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description= "Parse, and optionally output, details and data on UEFI-related firmware.")
    parser.add_argument('-b', "--brute", action="store_true", help= 'The input is a blob and may contain FV headers.')
    parser.add_argument('-c', "--capsule", action="store_true", help='The input file is a firmware capsule, do not search.')
    parser.add_argument('-f', "--ff", action="store_true", help='The input file is a firmware file.')
    parser.add_argument('-d', "--flash", action="store_true", help='The input file is a flash descriptor.')
    parser.add_argument('-m', "--me", action="store_true", help='The input file is an Intel ME container.')
    parser.add_argument('-p', "--pfs", action="store_true", help='The input file is a Dell PFS.HDR update.')

    parser.add_argument('-q', "--quiet", default=False, action="store_true", help="Do not show info.")
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
        
        if args.brute:
            if args.flash:
                brute_search_flash(input_data)
            else:
                brute_search_volumes(input_data)
            continue

        if args.ff:
            parse_file(input_data)
        elif args.capsule:
            parse_firmware_capsule(input_data)
        elif args.flash:
            parse_flash_descriptor(input_data)
        elif args.me:
            parse_me(input_data)
        elif args.pfs:
            parse_pfs(input_data)
        else:
            parse_firmware_volume(input_data) 





