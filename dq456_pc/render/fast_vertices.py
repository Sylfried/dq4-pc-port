"""Vertex data copied into pyglet's buffers in one block (memmove) instead of value by value.

pyglet 2.1 fills a vertex list's attribute (creation, `vl.position = a`, `vl.position[:] = a`) through a ctypes slice assignment: ctypes reads a numpy array
one value at a time (47 700 vertices of the DQ VI world map: 22 ms for the positions and texture coordinates, 44 ms to create the list, against 0.2 ms by memmove).
Every scene, sprite sheet, model, monster or menu that appears for the first time paid it, and so did the scenery animations at every frame.

`install()` (once, before the first vertex list) makes the three paths copy a numpy array of the right size in one block, converted to the attribute's type
(float32 for 'f'); anything else (lists, tuples, a wrong size, an int attribute fed with floats) goes through pyglet as before, errors included.
"""
import ctypes
import numpy as np

_DTYPES = {ctypes.c_float: np.float32, ctypes.c_double: np.float64, ctypes.c_byte: np.int8, ctypes.c_ubyte: np.uint8, ctypes.c_short: np.int16,
           ctypes.c_ushort: np.uint16, ctypes.c_int: np.int32, ctypes.c_uint: np.uint32}
_installed = False


def copy_into(buffer, start, count, data):
    """Copies `data` (numpy array, count vertices of buffer.count values) into the backed buffer at vertex `start` and marks the region to send. False when it is not such an array:
    the caller takes pyglet's own path."""
    if not isinstance(data, np.ndarray): return False
    dt = _DTYPES.get(buffer.c_type)
    if dt is None or data.size != buffer.count * count: return False
    if np.issubdtype(dt, np.integer) and not np.issubdtype(data.dtype, np.integer): return False          # (ctypes refuses floats for an int: keep its error)
    a = np.ascontiguousarray(data, dtype=dt)
    ctypes.memmove(buffer.data_ptr + buffer.stride * start, a.ctypes.data, a.nbytes)
    buffer.invalidate_region(start, count)
    return True


class Region:
    """What `vl.<attribute>` gives: the attribute's values in the buffer (the ctypes array pyglet gives, for reading and for any other assignment), with `[:] = numpy array` copied in one block."""
    __slots__ = ('_buffer', '_start', '_count')

    def __init__(self, buffer, start, count): self._buffer, self._start, self._count = buffer, start, count

    def _array(self): return self._buffer.get_region(self._start, self._count)

    def __setitem__(self, key, value):
        if isinstance(key, slice) and key == slice(None) and copy_into(self._buffer, self._start, self._count, value): return
        self._array()[key] = value

    def __getitem__(self, key): return self._array()[key]
    def __len__(self): return self._buffer.count * self._count
    def __iter__(self): return iter(self._array())
    def __buffer__(self, flags): return memoryview(self._array())
    def __array__(self, dtype=None, copy=None): return np.array(self._array(), dtype=dtype)
    def __getattr__(self, name): return getattr(self._array(), name)


def install():
    """Patches pyglet (2.1) once: the attribute properties of the vertex domains created from now on, VertexList.set_attribute_data and BackedBufferObject.set_region."""
    global _installed
    if _installed: return
    from pyglet.graphics import vertexdomain as VD
    from pyglet.graphics import vertexbuffer as VB
    if not all(hasattr(x, y) for x, y in ((VD, '_make_attribute_property'), (VD.VertexList, 'set_attribute_data'), (VB.BackedBufferObject, 'set_region'))): return          # (another pyglet: left as is)

    def make_property(name):
        def getter(self):
            buffer = self.domain.attrib_name_buffers[name]
            buffer.invalidate_region(self.start, self.count)          # (as pyglet: reading the attribute marks it to send)
            return Region(buffer, self.start, self.count)

        def setter(self, data):
            buffer = self.domain.attrib_name_buffers[name]
            buffer.set_region(self.start, self.count, data)
        return property(getter, setter)

    set_data = VD.VertexList.set_attribute_data

    def set_attribute_data(self, name, data):
        if copy_into(self.domain.attrib_name_buffers[name], self.start, self.count, data): return
        set_data(self, name, data)

    set_region = VB.BackedBufferObject.set_region

    def fast_set_region(self, start, count, data):
        if copy_into(self, start, count, data): return
        set_region(self, start, count, data)

    VD._make_attribute_property = make_property
    VD.VertexList.set_attribute_data = set_attribute_data
    VB.BackedBufferObject.set_region = fast_set_region
    _installed = True
