# -*- coding: utf-8 -*-

import argparse
import os

from uefi_firmware.uefi import *
from uefi_firmware.generator import uefi as uefi_generator
from uefi_firmware.utils import dump_data, flatten_firmware_objects

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
        return None
    
    pfs.process()
    return pfs

def parse_firmware_volume(data, name="volume"):
    print "Parsing FV at index (%s)." % name
    firmware_volume = FirmwareVolume(data, name)

    if not firmware_volume.valid_header:
        print "Error: Cannot parse file (%s) as a firmware volume." % args.file
        return None

    firmware_volume.process()
    return firmware_volume
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description= "Search a file for UEFI firmware volumes, parse and output.")
    #parser.add_argument('-f', "--firmware", action="store_true", help='The input file is a firmware volume.')
    #parser.add_argument('-b', "--brute", action="store_true", help= 'The input is a blob and may contain FV headers.')
    parser.add_argument('-c', "--capsule", action="store_true", help='The input file is a firmware capsule.')
    #parser.add_argument('-p', "--pfs", action="store_true", help='The input file is a Dell PFS.')
    
    ### Injection options
    parser.add_argument('--guid', default=None, help="GUID to replace (inject).")
    parser.add_argument('--injection', required= True, help="Pre-generated EFI file to inject.")
    parser.add_argument('-o', '--output', default= "injected.obj", help="Name of the output file.")

    parser.add_argument("file", help="The file to work on")
    args = parser.parse_args()
    
    try:
        with open(args.file, 'rb') as fh: input_data = fh.read()
    except Exception, e:
        print "Error: Cannot read file (%s) (%s)." % (args.file, str(e))
        sys.exit(1)

    try:
        with open(args.injection, 'rb') as fh: injection_data = fh.read()
    except Exception, e:
        print "Error: Cannot read file (%s) (%s)." % (args.injection, str(e))
        sys.exit(1)

    #if args.brute:
    #    parsed = brute_search(input_data)
    #elif args.capsule:
    #    pass
    #if args.pfs:
    #    parsed = parse_pfs(input_data)
    #else:
    #    parsed = parse_firmware_volume(input_data)
    parsed = parse_firmware_volume(input_data, name="input")
    if parsed is None:
        sys.exit(0)

    ### Iterate over each file object.
    objects = flatten_firmware_objects(parsed.iterate_objects(True))
    for firmware_object in objects:
        if firmware_object["guid"] == args.guid and type(firmware_object["_self"]) == FirmwareFile:
            print "Injecting (replacing) FirmwareFile %s." % green(args.guid)
            firmware_object["_self"].data = injection_data
            firmware_object["_self"].process()
    output_object = parsed.build()
    dump_data(args.output, output_object)




