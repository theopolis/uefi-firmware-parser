# -*- coding: utf-8 -*-

# Source: EFIPWN
# URL: https://github.com/G33KatWork/EFIPWN.git

import struct
import os
import sys

class BitArray(object):

    def __init__(self, data):
        self._Data = data
        
        self._DataBitsLeft = len(data) * 8

        self._ByteIdx = 0
        self._BitIdx = 0
    
    def mask(self, bitcount):
        return (1 << bitcount) - 1

    def read(self, bitsleftcount):

        result = 0
        bitsdonecount = 0
        while bitsleftcount:
            curbitsleftcount = 8 - self._BitIdx
            curdata = ord(self._Data[self._ByteIdx]) & self.mask(curbitsleftcount)
            
            if curbitsleftcount >= bitsleftcount:
                result <<= bitsleftcount        
                result |= curdata >> (curbitsleftcount - bitsleftcount)
                self._BitIdx += bitsleftcount
                bitsleftcount = 0
            else:
                result <<= curbitsleftcount
                result |= curdata
                bitsleftcount -= curbitsleftcount
                self._BitIdx += curbitsleftcount
            
            if self._BitIdx >= 8:
                self._BitIdx = 0
                self._ByteIdx += 1
                
        return result

def LoadHuffmanSyms(bits, symscountbits, zeroskipidx):
    huffsyms = None
    symscount = bits.read(symscountbits)
    if symscount == 0:
        v = bits.read(symscountbits)
        huffsyms = [ [ v, 1, 0], [ v, 1, 1 ] ]
    else:
        # Decode the horrible bit length encoding thing!
        huffsyms = []
        idx = 0
        while idx < symscount:
            bitlen = bits.read(3)
            if bitlen == 7:
                while bits.read(1):
                    bitlen += 1
            if bitlen != 0:
                huffsyms += ([idx, bitlen, None], )
            idx += 1
            
            # decode the extra special nasty zero-skip hack!
            if idx == zeroskipidx:
                idx += bits.read(2)
        
        # Now, sort them by bit length
        huffsyms = sorted(huffsyms, key=lambda length: length[1])

        # Allocate huffman codes to the length-ordered symbols
        huffsyms[0][2] = 0
        for idx in xrange(1, len(huffsyms)):
            huffsyms[idx][2] = (huffsyms[idx-1][2] + 1) << (huffsyms[idx][1] - huffsyms[idx-1][1])

    return huffsyms

def BuildHuffmanTree(huffsyms):
    hufftree = [None, None]
    for huffsym in huffsyms:
        symbol = huffsym[0]
        bitlen = huffsym[1]
        huffcode = huffsym[2]
        if bitlen == 0:
            continue

        huffsubtree = hufftree
        for bit in xrange(0, bitlen):
            lr = huffcode & (1 << (bitlen - bit - 1)) != 0

            if bit < bitlen - 1:
                if huffsubtree[lr] == None:
                    huffsubtree[lr] = [None, None]
                huffsubtree = huffsubtree[lr]
            else:
                huffsubtree[lr] = symbol
    return hufftree

def HuffmanDecode(hufftree, bits):
    while type(hufftree) == list:
        hufftree = hufftree[bits.read(1)]
    return hufftree

def LoadCharLenHuffmanSyms(bits, extra_hufftree):
    huffsyms = None
    symscount = bits.read(9)

    if symscount == 0:
        v = bits.read(9)
        huffsyms = [ [ v, 1, 0], [ v, 1, 1 ] ]
    else:
        # Decode the horrible bit length encoding thing!
        huffsyms = []
        idx = 0
        while idx < symscount:
            bitlen = HuffmanDecode(extra_hufftree, bits)
            
            if bitlen == 0:
                bitlen = 0
            elif bitlen == 1:
                idx += bits.read(4) + 3 - 1
                bitlen = 0
            elif bitlen == 2:
                idx += bits.read(9) + 20 - 1
                bitlen = 0
            else:
                bitlen -= 2
                
            if bitlen != 0:
                huffsyms += ([idx, bitlen, None], )
                
            idx += 1

        # Now, sort them by bit length
        huffsyms = sorted(huffsyms, key=lambda length: length[1])

        # Allocate huffman codes to the length-ordered symbols
        huffsyms[0][2] = 0
        for idx in xrange(1, len(huffsyms)):
            huffsyms[idx][2] = (huffsyms[idx-1][2] + 1) << (huffsyms[idx][1] - huffsyms[idx-1][1])

    return huffsyms

def Decompress(buf):
    (compressed_size, decompressed_size) =  struct.unpack("<II", buf[0:8])
    bits = BitArray(buf[8:])

    outbuf = ''
    blocksize = 0
    charlen_hufftree = None
    positionset_hufftree = None
    while decompressed_size:
        if blocksize == 0:    
            blocksize = bits.read(16)   
            extra_hufftree = BuildHuffmanTree(LoadHuffmanSyms(bits, 5, 3))
            charlen_hufftree = BuildHuffmanTree(LoadCharLenHuffmanSyms(bits, extra_hufftree))

            #positionset_hufftree = BuildHuffmanTree(LoadHuffmanSyms(bits, 4, -1))
            positionset_hufftree = BuildHuffmanTree(LoadHuffmanSyms(bits, 5, -1))

        c = HuffmanDecode(charlen_hufftree, bits)
        blocksize -= 1
        if c < 256:
            outbuf += chr(c)
            decompressed_size -= 1
        else:
            data_length = (c & 0xff) + 3
            pos_bitlen = HuffmanDecode(positionset_hufftree, bits)
            data_offset = pos_bitlen
            if pos_bitlen > 1:
                data_offset = (1 << (pos_bitlen - 1)) + bits.read(pos_bitlen - 1)
            data_idx = len(outbuf) - data_offset -1

            for i in xrange(0, data_length):
                outbuf += outbuf[data_idx+i]
            decompressed_size -= data_length

    return outbuf
