import os
import ctypes

from .utils import dump_data, sguid, blue

class BaseObject(object):
    '''A base object can be used to access direct content.'''

class FirmwareObject(object):
    data = None

    @property
    def content(self):
        if hasattr(self, "data"): return self.data
        return ""
    @property
    def objects(self):
        return []
    @property
    def label(self):
        if hasattr(self, "name"): 
            if self.name is None: return ""
            return self.name
        return ""

    @property
    def guid_label(self):
        if not hasattr(self, "guid"): return ""
        return sguid(self.guid)

    @property
    def type_label(self):
        return self.__class__.__name__

    @property
    def attrs_label(self):
        if hasattr(self, "attrs"): return self.attrs
        return {}

    def info(self, include_content= False):
        return {
            "_self": self,
            "label": self.label,
            "guid": self.guid_label,
            "type": self.type_label,
            "content": self.content if include_content else "",
            "attrs": self.attrs_label
        }   
    
    def iterate_objects(self, include_content= False):
        objects = []
        for _object in self.objects:
            if _object is None: continue
            _info = _object.info(include_content)
            _info["objects"] = _object.iterate_objects(include_content)
            for object in _info["objects"]: object["parent"] = _info
            objects.append(_info)
        return objects

class StructuredObject(object):
    def parse_structure(self, data, structure):
        '''Construct an instance object of the provided structure.'''
        struct_instance = structure()
        struct_size = ctypes.sizeof(struct_instance)

        struct_data = data[:struct_size]
        struct_length = min(len(struct_data), struct_size)
        ctypes.memmove(ctypes.addressof(struct_instance), struct_data, struct_length)
        self.structure = struct_instance
        self.structure_data = struct_data
        self.structure_fields = [field[0] for field in structure._fields_]
        self.structure_size = struct_size

    def show_structure(self):
        for field in self.fields:
            print "%s: %s" % (field, getattr(self.structure, field, None))

class RawObject(FirmwareObject, BaseObject):
    def __init__(self, data):
        self.data = data

    def build(self, generate_checksum, debug= False):
    	return self.data

    def showinfo(self, ts= '', index= None):
        print "%s%s size= %d " % (
            ts, blue("RawObject:"), len(self.data)
        )

    def dump(self, parent= '', index= None):
    	path = os.path.join(parent, "object.raw")
    	dump_data(path, self.data)
