#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse

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
        guid = firmware_object["guid"] if "guid" in firmware_object else None
        if guid is None:
            continue
        if firmware_object["guid"] in [v for k, v in FIRMWARE_GUIDED_GUIDS.items()]:
            guid = firmware_object["parent"]["parent"]["guid"]

        if len(guid) == 0:
            continue
        if guid not in list(guids.keys()):
            guids[guid] = {"labels": [], "types": []}

        if len(firmware_object["label"]) > 0 and \
                firmware_object["label"] not in guids[guid]["labels"]:
            guids[guid]["labels"].append(firmware_object["label"])
        if firmware_object["type"] not in guids[guid]["types"]:
            guids[guid]["types"].append(firmware_object["type"])

    guid_list = list(guids.keys())
    guid_list.sort()

    for guid in guid_list:
        guid_name = get_guid_name(s2aguid(guid))

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
    volumes = search_firmware_volumes(data)
    for index in volumes:
        parse_firmware_volume(data[index - 40:], name=index - 40)
    pass


def brute_search_flash(data):
    descriptors = search_flash_descriptor(data)
    for index in descriptors:
        parse_flash_descriptor(data[index:])
    pass


def parse_firmware_capsule(data, name=0):
    firmware_capsule = FirmwareCapsule(data, name)
    if not firmware_capsule.valid_header:
        return
    firmware_capsule.process()
    pass


def parse_firmware_volume(data, name=0):
    firmware_volume = FirmwareVolume(data, name)
    firmware_volume.process()
    list_uefi_guids(firmware_volume)


def parse_flash_descriptor(data):
    flash = FlashDescriptor(data)
    if not flash.valid_header:
        return
    flash.process()
    list_uefi_guids(flash)

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
            brute_search_flash(input_data)
        else:
            brute_search_volumes(input_data)
        sys.exit(1)

    if args.capsule:
        parse_firmware_capsule(input_data)
    elif args.flash:
        parse_flash_descriptor(input_data)
    else:
        parse_firmware_volume(input_data)
