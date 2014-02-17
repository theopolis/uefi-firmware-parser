import tempfile
import subprocess
import os

# Not the best way to accomplish the job...
def p7z_extract(data):
    '''Use 7z to decompress an LZMA-compressed section.'''
    uncompressed_data = None
    with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp.write(data)
        temp.flush()
        subprocess.call(["7zr", "-o/tmp", "e", temp.name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with open("%s~" % temp.name, 'r') as fh: uncompressed_data = fh.read()
        os.unlink("%s~" % temp.name)
    
    return uncompressed_data
    pass
