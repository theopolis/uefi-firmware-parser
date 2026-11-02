#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import sys
import uuid

from uefi_firmware.uefi import *
from uefi_firmware.utils import *
from uefi_firmware.flash import FlashDescriptor
from uefi_firmware.guids import get_guid_name


def debug(text, cr=True, gen=False):
    if args.generate is not None and not gen:
        return
    if args.generate is None and gen:
        return
    elif cr:
        print(text)
    else:
        print(text, end=' ')


def label_as_guid_name(label):
    if args.generate is None:
        return None

    def is_cap(c):
        if ord(c) >= ord('A') and ord(c) <= ord('Z'):
            return True
        return False

    producer = ""
    for i in range(len(label)):
        if label[i] == '_':
            continue
        if i > 0:
            if is_cap(label[i]) and not is_cap(label[i - 1]):
                producer += "_"
        producer += label[i]
    if len(producer) == 0:
        return None
    if producer.lower().find(args.generate.lower()) != 0:
        producer = "%s_%s" % (args.generate, producer)
    return "%s_GUID" % producer.upper().replace(".EFI", "")


def list_uefi_guids(base_object):
    base_objects = base_object.iterate_objects(False)
    objects = flatten_firmware_objects(base_objects)
    guids = {}

    for firmware_object in objects:
        guid = firmware_object.get("guid")
        if not guid:
            continue
        if guid in FIRMWARE_GUIDED_GUIDS.values():
            # Report the file that holds a GUID-defined section.
            file_object = firmware_object.get("parent", {}).get("parent", {})
            guid = file_object.get("guid")
            if not guid:
                continue

        if guid not in guids:
            guids[guid] = {"labels": [], "types": []}

        label = firmware_object.get("label")
        if label and label not in guids[guid]["labels"]:
            guids[guid]["labels"].append(label)
        guid_type = firmware_object.get("type")
        if guid_type and guid_type not in guids[guid]["types"]:
            guids[guid]["types"].append(guid_type)

    guid_list = list(guids.keys())
    guid_list.sort()

    for guid in guid_list:
        guid_name = get_guid_name(uuid.UUID(guid).bytes_le)

        label = ""
        if len(guids[guid]["labels"]) >= 1:
            label = guids[guid]["labels"][0]

        if guid_name is not None:
            debug(guid_name, False)
        else:
            debug("Unknown", False)
            generated_label = label_as_guid_name(label)
            if generated_label is not None or args.unknowns:
                if args.unknowns and generated_label is None:
                    generated_label = "__UNKNOWN__"
                debug("\"%s\": %s," %
                      (generated_label, s2aguid(guid)), True, True)

        debug(green(guid), False)
        debug(", ".join([purple(_label)
                         for _label in guids[guid]["labels"]]), False)
        debug(", ".join([blue(guid_type)
                         for guid_type in guids[guid]["types"]]))
    pass


def brute_search_volumes(data):
    found = False
    for index in search_firmware_volumes(data):
        # The '_FVH' signature is 40 bytes into the volume header.
        if index < 40:
            continue
        found = parse_firmware_volume(data[index - 40:], name=index - 40) or \
            found
    return found


def brute_search_flash(data):
    # The flash signature is 16 bytes into the descriptor.
    found = False
    index = data.find(FLASH_HEADER, 0x10)
    while index >= 0:
        found = parse_flash_descriptor(data[index - 0x10:]) or found
        index = data.find(FLASH_HEADER, index + 1)
    return found


def parse_firmware_capsule(data, name=0):
    firmware_capsule = FirmwareCapsule(data, name)
    if not firmware_capsule.valid_header or not firmware_capsule.process():
        print("Error: cannot parse %s as a firmware capsule." % args.file)
        return False
    list_uefi_guids(firmware_capsule)
    return True


def parse_firmware_volume(data, name=0):
    firmware_volume = FirmwareVolume(data, name)
    if not firmware_volume.valid_header or not firmware_volume.process():
        if not args.brute:
            print("Error: cannot parse %s as a firmware volume." % args.file)
        return False
    list_uefi_guids(firmware_volume)
    return True


def parse_flash_descriptor(data):
    flash = FlashDescriptor(data)
    if not flash.valid_header or not flash.process():
        if not args.brute:
            print("Error: cannot parse %s as a flash descriptor." % args.file)
        return False
    list_uefi_guids(flash)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Output GUIDs for files, optionally write GUID structure file.")
    parser.add_argument(
        '-c', "--capsule", action="store_true",
        help='The input file is a firmware capsule, do not search.')
    parser.add_argument(
        '-b', "--brute", action="store_true",
        help='The input file is a blob, search for firmware volume headers.')
    parser.add_argument(
        '-d', "--flash", action="store_true",
        help='The input file is a flash descriptor.')

    parser.add_argument(
        '-g', "--generate", default=None,
        help="Generate a behemonth-style GUID output.")
    parser.add_argument(
        '-u', "--unknowns", action="store_true",
        help='When generating also print unknowns.')

    parser.add_argument("file", help="The file to work on")
    args = parser.parse_args()

    try:
        with open(args.file, 'rb') as fh:
            input_data = fh.read()
    except Exception as e:
        print("Error: Cannot read file (%s) (%s)." % (args.file, str(e)))
        sys.exit(1)

    if args.brute:
        if args.flash:
            found = brute_search_flash(input_data)
        else:
            found = brute_search_volumes(input_data)
    elif args.capsule:
        found = parse_firmware_capsule(input_data)
    elif args.flash:
        found = parse_flash_descriptor(input_data)
    else:
        found = parse_firmware_volume(input_data)
    sys.exit(0 if found else 1)
