UEFI Firmware Parser
====================
The UEFI firmware parser is a simple module and set of scripts for parsing, extracting, and recreating UEFI firmware volumes.
This includes parsing modules for BIOS, OptionROM, Intel ME and other formats too. 
Please use the example scripts for parsing tutorials.

Installation
------------
::

  $ sudo python ./setup.py install

**Requirements**

- The 7-zip binary ``7zr`` is used for LZMA decompression.
- ``pefile`` is optional, and may be used for additional parsing.

Usage
-----
Example scripts are provided in ``/scripts``

::

  $ python ./scripts/fv_parser.py -h

  usage: fv_parser.py [-h] [-f] [-o OUTPUT] [-e] file

  Search a file for UEFI firmware volumes, parse and output.

  positional arguments:
    file                  The file to work on

  optional arguments:
    -h, --help            show this help message and exit
    -f, --firmware        The input file is a firmware volume, do not search.
    -o OUTPUT, --output OUTPUT
                          Dump EFI Files to this folder.
    -e, --extract         Extract all files/sections/volumes.

