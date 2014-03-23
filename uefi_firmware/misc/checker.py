"""
These are misc functions/classes to implement several type checkers.
The TypeTester may be useful if parsing a large number of UEFI-related binaries.
"""

import re

class TypeTester(object):
  static = "MZ"

  def match(self, data):
    if data[:self.size] == self.static:
      return True
    return False
  @property
  def size(self):
    return len(self.static)
  @property
  def name(self):
    return self.__class__.__name__

class EfiCapsuleTester(TypeTester):
  static = "".join("BD 86 66 3B 76 0D 30 40 B7 0E B5 51 9E 2F C5 A0".split(" ")).decode('hex')
class UefiCapsuleTester(TypeTester):
  static = "".join("B9 82 91 53 B5 AB 91 43 B6 9A E3 A9 43 F7 2F CC".split(" ")).decode('hex')
class MeManifestTester(TypeTester):
  static = "".join("04 00 00 00 A1 00 00 00".split(" ")).decode('hex')
class DellPFSTester(TypeTester):
  static = "PFS.HDR"

class DellUpdateBinary(TypeTester):
  hdr_pattern = re.compile(r'.{4}\xAA\xEE\xAA\x76\x1B\xEC\xBB\x20\xF1\xE6\x51.{1}\x78\x9C')
  static = "\x00"*100
  def match(self, data):
    hdr_match = self.hdr_pattern.search(data)
    if hdr_match is None:
      return False
    return True

TESTERS = [
  UefiCapsuleTester, EfiCapsuleTester,
  MeManifestTester,
  DellPFSTester, DellUpdateBinary
]