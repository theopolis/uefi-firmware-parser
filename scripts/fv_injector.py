#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse

from uefi_firmware.uefi import *
from uefi_firmware.utils import dump_data, flatten_firmware_objects

from uefi_firmware.pfs import PFSFile


def brute_search(data):
    volumes = search_firmware_volumes(data)

    for index in volumes:
        _parse_firmware_volume(data[index - 40:], name=index - 40)
    pass


def parse_pfs(data):
    pfs = PFSFile(data)
    if not pfs.check_header():
        print("Error: Cannot parse file (%s) as a Dell PFS." % args.file)
        return None

    pfs.process()
    return pfs


def parse_firmware_volume(data, name="volume"):
    print("Parsing FV at index (%s)." % name)
    firmware_volume = FirmwareVolume(data, name)

    if not firmware_volume.valid_header:
        print("Error: Cannot parse file (%s) as a firmware volume." % args.file)
        return None

    firmware_volume.process()
    return firmware_volume


def parse_file(data):
    obj_references = []

    def _print_obj(obj):
        obj_references.append(obj["_self"])
        print("[%d] %s: %s" % (len(obj_references), str(obj["_self"]), str(obj["attrs"])))
        if "objects" in obj and len(obj["objects"]) > 0:
            for sub_obj in obj["objects"]:
                _print_obj(sub_obj)

    ff = FirmwareFile(data)
    if not ff.process():
        print("[!] Error: Cannot parse FirmwareFile.")
        return None

    objects = ff.iterate_objects(include_content=False)
    for obj in objects:
        _print_obj(obj)
    selection = 0

    while True:
        selection = input(
            "[#] Replace what section: [1-%d]: " % len(obj_references))
        try:
            selection = int(selection)
            if selection < 1 or selection > len(obj_references):
                print("[!] Try again...")
                continue
            break
        except:
            print("[!] Try again...")
            continue
        pass
    return (ff, obj_references, selection)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Search a file for UEFI firmware volumes, parse and output.")
    parser.add_argument(
        '-c', "--capsule", action="store_true", default=False,
        help='The input file is a firmware capsule.')
    parser.add_argument(
        '-p', "--pfs", action="store_true", default=False,
        help='The input file is a Dell PFS.')
    parser.add_argument(
        "-f", "--ff", action="store_true", default=False,
        help="Inject payload into firmware file.")

    # Injection options
    parser.add_argument(
        '--guid', default=None,
        help="GUID to replace (inject).")
    parser.add_argument(
        '--injection', required=True,
        help="Pre-generated EFI file to inject.")
    parser.add_argument(
        '-o', '--output', default="injected.obj",
        help="Name of the output file.")

    parser.add_argument("file", help="The file to work on")
    args = parser.parse_args()

    try:
        with open(args.file, 'rb') as fh:
            input_data = fh.read()
    except Exception as e:
        print("Error: Cannot read file (%s) (%s)." % (args.file, str(e)))
        sys.exit(1)

    try:
        with open(args.injection, 'rb') as fh:
            injection_data = fh.read()
    except Exception as e:
        print("Error: Cannot read file (%s) (%s)." % (args.injection, str(e)))
        sys.exit(1)

    # Special case, regenerate a file.
    if args.ff:
        print("[#] Opening firmware file.")
        parsed = parse_file(input_data)
        firmware_file = parsed[0]
        objects = parsed[1]
        index = parsed[2]
        print("[#] Regenerating firmware file with injected section payload.")
        objects[index - 1].regen(injection_data)
        print("[#] Re-parsing firmware file objects.")
        objects[index - 1].process()
        print("[#] Rebuilding firmware objects.")
        output_object = firmware_file.build()
        print("[#] Rebuild complete, injection successful.")
        dump_data(args.output, output_object[1])
        print("[#] Injected firmware written to %s." % args.output)
        sys.exit(0)

    if args.pfs:
        print("[#] Opening firmware as Dell PFS.")
        parsed = parse_pfs(input_data)
    else:
        print("[#] Opening firmware as UEFI firmware volume.")
        parsed = parse_firmware_volume(input_data)
    if parsed is None:
        sys.exit(0)

    # Iterate over each file object.
    objects = flatten_firmware_objects(parsed.iterate_objects(True))
    print("[#] Firmware objects parsed.")
    for firmware_object in objects:
        if firmware_object["guid"] == args.guid and type(firmware_object["_self"]) == FirmwareFile:
            print("[#] Injecting (replacing) FirmwareFile %s." % green(args.guid))
            #firmware_object["_self"].data = injection_data
            firmware_object["_self"].regen(injection_data)
            print("[#] Regenerating firmware children structures (from injection point).")
            firmware_object["_self"].process()
            print("[#] Regeneration complete, child objects parsed.")
    print("[#] Rebuilding complete firmware with injection.")
    output_object = parsed.build()
    print("[#] Rebuild complete, injection successful.")
    dump_data(args.output, output_object)
    print("[#] Injected firmware written to %s." % args.output)
