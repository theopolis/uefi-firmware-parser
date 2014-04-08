import os
from .utils import dump_data, fguid

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
        return fguid(self.guid)
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
            objects.append(_info)
        return objects

class RawObject(FirmwareObject):
    def __init__(self, data):
        self.data = data
    def build(self, generate_checksum, debug= False):
    	return self.data
    def showinfo(self, ts= '', index= None):
    	pass
    def dump(self, parent= '', index= None):
    	#path = os.path.join(parent, "object.raw")
    	#dump_data(path, self.data)
    	pass
    pass
