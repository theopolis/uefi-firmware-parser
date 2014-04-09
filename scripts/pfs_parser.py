# -*- coding: utf-8 -*-

# Dell PFS Firmware Update Parser
# Copyright Teddy Reed (teddy@prosauce.org)
#
# This script attempts to parse a DELL HDR file (BIOS/UEFI update).
# Newer versions of the DELL HDR format (see contrib script for extracting 
# from an update executable) use a PFS.HDR. magic value. The data seems to 
# have packed sections, the first of which contains a UEFI Firmware Volume. 
# By analyzing update sets, latter updates contain details/binary following
# each chunk. 

import argparse

import sys
import os

from uefi_firmware.pfs import PFSFile

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description= "Parse a Dell PFS update.")
    parser.add_argument('-o', "--output", default=".", help="Dump EFI Files to this folder.")
    parser.add_argument("-e", "--extract", action="store_true", default=False, help="Dump all PFS sections.")
    
    parser.add_argument("file", help="The file to work on")
    args = parser.parse_args()
    
    try:
        with open(args.file, 'rb') as fh: input_data = fh.read()
    except Exception, e:
        print "Error: Cannot read file (%s) (%s)." % (args.file, str(e))
        sys.exit(1)
        
    pfs = PFSFile(input_data)
    if not pfs.check_header():
      sys.exit(1)

    pfs.process()
    pfs.showinfo()

    if args.extract:
      pfs.dump(args.output)