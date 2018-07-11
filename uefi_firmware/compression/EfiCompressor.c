// This is an open source non-commercial project. Dear PVS-Studio, please check it.
// PVS-Studio Static Code Analyzer for C, C++ and C#: http://www.viva64.com
/** @file

Copyright (c) 2009 - 2010, Intel Corporation. All rights reserved.<BR>
This program and the accompanying materials are licensed and made available 
under the terms and conditions of the BSD License which accompanies this 
distribution.  The full text of the license may be found at
http://opensource.org/licenses/bsd-license.php

THE PROGRAM IS DISTRIBUTED UNDER THE BSD LICENSE ON AN "AS IS" BASIS,
WITHOUT WARRANTIES OR REPRESENTATIONS OF ANY KIND, EITHER EXPRESS OR IMPLIED.

Modified for uefi_firmware_parser:
This includes minor API changes for Tiano and EFI decompressor, as well as LZMA.

**/

#include <Python.h>

#include "CompressionTypes.h"

#include "Tiano/Decompress.h"
#include "Tiano/Compress.h"
#include "LZMA/LzmaDecompress.h"
#include "LZMA/LzmaCompress.h"

#define EFI_COMPRESSION   1 //defined as PI_STD, section type= 0x01
#define TIANO_COMPRESSION 2 //not defined, section type= 0x01
#define LZMA_COMPRESSION  3 //not defined, section type= 0x02

#define MAX_DSTSZ 40000000 //40MB -- Max destination buffer size allowed. 
                           //I don't think there is an image to decompress bigger than this. In any case, feel free to change.

EFI_STATUS
Extract (
  IN      VOID    *Source,
  IN      SizeT   SrcSize,
     OUT  VOID    **Destination,
     OUT  SizeT   *DstSize,
  IN      UINTN   Algorithm
  )
{
  VOID          *Scratch;
  SizeT         ScratchSize;
  EFI_STATUS    Status;

  GETINFO_FUNCTION    GetInfoFunction;
  DECOMPRESS_FUNCTION DecompressFunction;

  GetInfoFunction = NULL;
  DecompressFunction = NULL;
  Scratch = NULL;
  ScratchSize = 0;
  Status = EFI_SUCCESS;

  switch (Algorithm) {
  case 0:
    *Destination = (VOID *)malloc(SrcSize);
    if (*Destination != NULL) {
      memcpy(*Destination, Source, SrcSize);
    } else {
      Status = EFI_OUT_OF_RESOURCES;
    }
    break;
  case EFI_COMPRESSION:
    GetInfoFunction = EfiGetInfo;
    DecompressFunction = EfiDecompress;
    break;
  case TIANO_COMPRESSION:
    GetInfoFunction = TianoGetInfo;
    DecompressFunction = TianoDecompress;
    break;
  case LZMA_COMPRESSION:
    GetInfoFunction = LzmaGetInfo;
    DecompressFunction = LzmaDecompress;
    break;
  default:
    Status = EFI_INVALID_PARAMETER;
  }
  if (GetInfoFunction != NULL) {
    Status = GetInfoFunction(Source, SrcSize, DstSize, &ScratchSize);
    if (Status == EFI_SUCCESS) {
      if (ScratchSize > 0) {
        Scratch = (VOID *)malloc(ScratchSize);
      }
      if(*DstSize <= MAX_DSTSZ){
        *Destination = (VOID *)malloc(*DstSize);
      }
      if (((ScratchSize > 0 && Scratch != NULL) || ScratchSize == 0) && *Destination != NULL) {
        Status = DecompressFunction(Source, SrcSize, *Destination, *DstSize, Scratch, ScratchSize);
      } else {
        free(*Destination);
        free(Scratch);
        Status = EFI_OUT_OF_RESOURCES;
      }
    }
  }
  return Status;
}

void 
errorHandling(
  VOID* SrcBuf,
  VOID* DstBuf
  )
{
  free(DstBuf);
}

/*
 UefiDecompress(data_buffer, size, huffman_type)
*/
STATIC
PyObject*
UefiDecompress(
  PyObject    *Self,
  PyObject    *Args,
  UINT8       type
  )
{
  PyBytesObject *SrcData;
  SizeT         SrcDataSize;
  SizeT         DstDataSize;
  EFI_STATUS    Status;
  char          *SrcBuf;
  char          *DstBuf;

  DstDataSize = 0;
  DstBuf = NULL;

  Status = PyArg_ParseTuple(Args, "OK", &SrcData, &SrcDataSize); //-V111
  if (Status == 0) {
    return NULL;
  }

  SrcBuf = SrcData->ob_sval;

  Status = Extract((VOID *)SrcBuf, SrcDataSize, (VOID **)&DstBuf, &DstDataSize, type);
  if (Status != EFI_SUCCESS) {
    PyErr_SetString(PyExc_Exception, "Failed to decompress\n");
    errorHandling(SrcBuf, DstBuf);
    return NULL;
  }

  return PyBytes_FromStringAndSize(DstBuf, (Py_ssize_t)DstDataSize);
}

/*
 UefiCompress(data_buffer, size, huffman_type)
*/
STATIC
PyObject*
UefiCompress(
  PyObject    *Self,
  PyObject    *Args,
  UINT8       type
  )
{
  PyBytesObject *SrcData;
  SizeT         SrcDataSize;
  SizeT         DstDataSize;
  EFI_STATUS    Status;
  char          *SrcBuf;
  char          *DstBuf;

  // Pick the compress function based on compression type
  COMPRESS_FUNCTION CompressFunction;

  DstDataSize = 0;
  DstBuf = NULL;
  CompressFunction = NULL;

  Status = PyArg_ParseTuple(Args, "OK", &SrcData, &SrcDataSize); //-V111
  if (Status == 0) {
    return NULL;
  }

  SrcBuf = SrcData->ob_sval;

  if (type == LZMA_COMPRESSION) {
    CompressFunction = (COMPRESS_FUNCTION) LzmaCompress;
  } else {
    CompressFunction = (COMPRESS_FUNCTION) ((type == EFI_COMPRESSION) ? EfiCompress : TianoCompress);
  }
  Status = CompressFunction(SrcBuf, SrcDataSize, DstBuf, &DstDataSize);
  if (Status == EFI_BUFFER_TOO_SMALL) {
    // The first call to compress fills in the expected destination size.
    DstBuf = malloc (DstDataSize);
    if (!DstBuf) {
      errorHandling(SrcBuf, DstBuf);
      return NULL;
    }
    // The second call to compress compresses.
    Status = CompressFunction(SrcBuf, SrcDataSize, DstBuf, &DstDataSize);
  }

  if (Status != EFI_SUCCESS) {
    PyErr_SetString(PyExc_Exception, "Failed to compress\n");
    errorHandling(SrcBuf, DstBuf);
    return NULL;
  }

  return PyBytes_FromStringAndSize(DstBuf, (Py_ssize_t)DstDataSize);
}

/**

The following functions are semi-cyclic, they call a Python-abstraction that calls
replica version of the following two entry points. Each uses a cased short to determine
the huffman-decode implementation.

**/

STATIC
PyObject*
Py_EfiDecompress(
  PyObject    *Self,
  PyObject    *Args
  )
{
  /* Use the "EFI"-type compression, or PI_STD (4-bit symbol tables). */
  return UefiDecompress(Self, Args, EFI_COMPRESSION);
}

STATIC
PyObject*
Py_TianoDecompress(
  PyObject    *Self,
  PyObject    *Args
  )
{
  /* Use the "Tiano"-type compression (5-bit symbol tables). */
  return UefiDecompress(Self, Args, TIANO_COMPRESSION);
}

STATIC
PyObject*
Py_LzmaDecompress(
  PyObject    *Self,
  PyObject    *Args
  )
{
  /* Use the "Tiano"-type compression (5-bit symbol tables). */
  return UefiDecompress(Self, Args, LZMA_COMPRESSION);
}

STATIC
PyObject*
Py_EfiCompress(
  PyObject    *Self,
  PyObject    *Args
  )
{
  /* Use the "EFI"-type compression, or PI_STD (4-bit symbol tables). */
  return UefiCompress(Self, Args, EFI_COMPRESSION);
}

STATIC
PyObject*
Py_TianoCompress(
  PyObject    *Self,
  PyObject    *Args
  )
{
  /* Use the "Tiano"-type compression (5-bit symbol tables). */
  return UefiCompress(Self, Args, TIANO_COMPRESSION);
}

STATIC
PyObject*
Py_LzmaCompress(
  PyObject    *Self,
  PyObject    *Args
  )
{
  /* Use the "Tiano"-type compression (5-bit symbol tables). */
  return UefiCompress(Self, Args, LZMA_COMPRESSION);
}

#define EFI_DECOMPRESS_DOCS   "EfiDecompress(): Decompress data using the EDKII standard algorithm.\n"
#define TIANO_DECOMPRESS_DOCS "TianoDecompress(): Decompress data using 5-bit Huffman encoding.\n"
#define LZMA_DECOMPRESS_DOCS  "LzmaDecompress(): Decompress using 7-z LZMA alogrithm.\n"
#define EFI_COMPRESS_DOCS     "EfiCompress(): Compress data using the EDKII standard algorithm.\n"
#define TIANO_COMPRESS_DOCS   "TianoCompress(): Compress data using 5-bit Huffman encoding.\n"
#define LZMA_COMPRESS_DOCS    "LzmaCompress(): Compress using 7-z LZMA alogrithm.\n"


STATIC PyMethodDef EfiCompressor_Funcs[] = {
  {"EfiDecompress",   (PyCFunction)Py_EfiDecompress,   METH_VARARGS, EFI_DECOMPRESS_DOCS},
  {"TianoDecompress", (PyCFunction)Py_TianoDecompress, METH_VARARGS, TIANO_DECOMPRESS_DOCS},
  {"LzmaDecompress",  (PyCFunction)Py_LzmaDecompress,  METH_VARARGS, LZMA_DECOMPRESS_DOCS},
  {"EfiCompress",     (PyCFunction)Py_EfiCompress,     METH_VARARGS, EFI_COMPRESS_DOCS},
  {"TianoCompress",   (PyCFunction)Py_TianoCompress,   METH_VARARGS, TIANO_COMPRESS_DOCS},
  {"LzmaCompress",    (PyCFunction)Py_LzmaCompress,    METH_VARARGS, LZMA_COMPRESS_DOCS},

  {NULL, NULL, 0, NULL}
};

#if PY_MAJOR_VERSION >= 3
STATIC PyModuleDef EfiCompressor = {
  PyModuleDef_HEAD_INIT,
  "efi_compressor",
  "Various EFI Compression Algorithms Extension Module",
  -1,
  EfiCompressor_Funcs
};

PyMODINIT_FUNC
PyInit_efi_compressor(VOID) {
  return PyModule_Create(&EfiCompressor);
}
#else
PyMODINIT_FUNC
initefi_compressor(VOID) {
  Py_InitModule3("efi_compressor", EfiCompressor_Funcs, "Various EFI Compression Algorithms Extension Module");
}
#endif


