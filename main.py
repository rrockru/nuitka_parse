#!/usr/bin/env python3

import struct
from typing import BinaryIO

CONSTANTS_BIN = "launcher_unpacked/__constants.bin"
DEBUG_LEVEL = 0

def read_bytes_zero_terminated(f: BinaryIO) -> bytes:
    buf = bytearray()
    while True:
        c = f.read(1)
        if c == b'\x00':
            break
        buf += c
    return bytes(buf)

def read_string(f: BinaryIO) -> str:
    return read_bytes_zero_terminated(f).decode("utf-8")

def read_byte(f: BinaryIO) -> bytes:
    return bytes(f.read(1))

def read_char(f: BinaryIO) -> str:
    return read_byte(f).decode("utf-8")

def read_uint8(f: BinaryIO) -> int:
    return int.from_bytes(f.read(1), "little")

def unpackValueUint16(f: BinaryIO) -> int:
    return int.from_bytes(f.read(2), "little")

def unpackValueUint32(f: BinaryIO) -> int:
    return int.from_bytes(f.read(4), "little")

def read_double(f: BinaryIO) -> float:
    return struct.unpack("<d", f.read(8))[0]

def read_variable_length(f: BinaryIO) -> int:
    result = 0
    factor = 1
    while True:
        byte = f.read(1)
        if not byte:
            raise Exception("Unexpected end of file while reading variable length integer")
        byte_value = byte[0]
        result += (byte_value & 0x7F) * factor
        if byte_value < 128:
            break
        factor <<= 7
    return result

class Constant:
    def __init__(self, constant_type, constant_value, constant_position):
        self.type = constant_type
        self.value = constant_value
        self.position = constant_position

    def __str__(self):
        return f"{self.value}: {self.type}"

def unpackBlobConstant(f: BinaryIO) -> Constant:
    constant_position = f.tell()
    constant_type = f.read(1)

    if DEBUG_LEVEL >= 9:
        print(f"Reading constant type {constant_type} at position 0x{constant_position:08X}")

    match constant_type:
        case b'A':
            # Alias type
            consts = [unpackBlobConstant(f) for _ in range(2)]
            return Constant('Alias', f'({consts[0].value}, {consts[1].value})', constant_position)
        case b'B':
            # Bytearray
            size = read_variable_length(f)
            return Constant('Bytearray', f'bytearray({f.read(size)})', constant_position)
        case b'D':
            # Dictionary
            size = read_variable_length(f)
            keys = [unpackBlobConstant(f) for _ in range(size)]
            value = [unpackBlobConstant(f) for _ in range(size)]
            return Constant('Dictionary', f'{{{", ".join(f"{keys[i].value}: {value[i].value}" for i in range(size))}}}', constant_position)
        case b'E':
            # Builtin exception
            return Constant('BuiltinException', read_string(f), constant_position)
        case b'F':
            # False
            return Constant('Boolean', False, constant_position)
        case b'G' | b'g':
            # Bignum, positive or negative
            size = read_variable_length(f)
            shift = 31
            value = 0
            for i in range(size):
                value <<= shift
                value += read_variable_length(f)
            return Constant('Bignum', value if constant_type == b'g' else -value, constant_position)
        case b'L':
            # List
            size = read_variable_length(f)            
            return Constant('List', f'[{", ".join(str(unpackBlobConstant(f)) for _ in range(size))}]', constant_position)
        case b'O':
            # Builtin object
            return Constant('BuiltinObject', read_string(f), constant_position)
        case b'P' | b'S':
            # Set or frozenset
            size = read_variable_length(f)
            return Constant('Set', f'{{{", ".join(str(unpackBlobConstant(f)) for _ in range(size))}}}', constant_position)
        case b'Q':
            # Special value
            value_type = read_uint8(f)
            match value_type:
                case 0:
                    return Constant('SpecialValue', '__builtin__.Ellipsis', constant_position)
                case 1:
                    return Constant('SpecialValue', '__builtin__.NotImplemented', constant_position)
                case 2:
                    return Constant('SpecialValue', '<Py_SysVersionInfo>', constant_position)
                case _:
                    raise Exception(f"Unknown special value type at {f.tell() - 1:08X}: {value_type}")
        case b'T':
            # Tuple
            return Constant('Tuple', f'({", ".join(str(unpackBlobConstant(f)) for _ in range(read_variable_length(f)))})', constant_position)
        case b'X':
            # Blob data pointer
            size = read_variable_length(f)
            f.seek(f.tell() + size)
            return Constant('BlobDataPointer', f'size: {size} bytes, position: 0x{f.tell() - size:08X}', f.tell() - size)
        case b'Z':
            # Constant double
            value_type = read_uint8(f)
            match value_type:
                case 0:
                    return Constant('ConstantDouble', 0.0, constant_position)
                case 1:
                    return Constant('ConstantDouble', -0.0, constant_position)
                case 2:
                    return Constant('ConstantDouble', float('NaN'), constant_position)
                case 3:
                    return Constant('ConstantDouble', -float('NaN'), constant_position)
                case 4:
                    return Constant('ConstantDouble', float('inf'), constant_position)
                case 5:
                    return Constant('ConstantDouble', -float('inf'), constant_position)
                case _:
                    raise Exception(f"Unknown constant double type at {f.tell() - 1:08X}: {value_type}")
        case b'a' | b'u':
            # String (ASCII or UTF-8)
            return Constant('String', read_string(f), constant_position)
        case b'b':
            # Bytes
            size = read_variable_length(f)
            return Constant('Bytes', bytes(f.read(size)), constant_position)
        case b'c':
            # Bytes, zero-terminated
            return Constant('BytesZeroTerminated', read_bytes_zero_terminated(f), constant_position)
        case b'd':
            # Byte, unsigned integer
            return Constant('Byte', read_byte(f), constant_position)
        case b'f':
            # Float
            return Constant('Float', read_double(f), constant_position)
        case b'n':
            # None
            return Constant('None', None, constant_position)
        case b'p':
            # Previous constant
            return Constant('PreviousConstant', "<previous constant>", constant_position)
        case b'q' | b'l':
            # Positive or negative integer value with abs value < 2**31
            value = read_variable_length(f)
            return Constant('Integer', value if type == b'l' else -value, constant_position)
        case b's':
            # Empty string
            return Constant('String', "\"\"", constant_position)
        case b't':     
            # True
            return Constant('Boolean', True, constant_position)
        case b'w':
            # Single character
            return Constant('Char', read_char(f), constant_position)
        case b':':
            # List of 3 constants
            return Constant('List of 3', f'[{", ".join(str(unpackBlobConstant(f)) for _ in range(3))}]', constant_position)
        case b';':
            # Range object
            start = unpackBlobConstant(f)
            stop = unpackBlobConstant(f)
            step = unpackBlobConstant(f)
            return Constant('Range', f'range({start}, {stop}, {step})', constant_position)
        case b'.':
            raise Exception(f"Missing blob value type '.' at position 0x{constant_position:08X}")
        case _:
            raise Exception(f"Unknown type at {f.tell() - 1:08X}: {type}")

class ConstantBlob:
    def __init__(self, f: BinaryIO):
        self.position = f.tell()
        self.name = read_string(f)
        self.size = unpackValueUint32(f)
        self.constant_count = unpackValueUint16(f)        

        if DEBUG_LEVEL >= 2:
            print(f'Parsing blob name: {self.name}, size: {self.size} bytes, position: 0x{self.position:08X}, constant count: {self.constant_count}')

        self.constants = [unpackBlobConstant(f) for _ in range(self.constant_count)]

class ConstantsBlobParser:
    def __init__(self, f: BinaryIO):
        self.file_hash = unpackValueUint32(f)
        self.file_size = unpackValueUint32(f) + 8
        self.blobs = {}
        while f.tell() < self.file_size - 1:
            blob = ConstantBlob(f)
            self.blobs[blob.name] = blob
            f.seek(f.tell() + 1) # Skip blob separator (.)

    def get(self, blob_name: str) -> ConstantBlob:
        return self.blobs[blob_name]

def main():
    print("Parsing constants blob...")
    f = open(CONSTANTS_BIN, "rb")
    blob = ConstantsBlobParser(f)
    f.close()

    # Print constants blob information
    print(f"File hash: 0x{blob.file_hash:08X}, file size: {blob.file_size} bytes, blob count: {len(blob.blobs)}")

    # Print .bytecode blob information
    bytecode_blob = blob.get(".bytecode")
    print(f"Blob name: {bytecode_blob.name}, size: {bytecode_blob.size} bytes, position: 0x{bytecode_blob.position:08X}, constant count: {bytecode_blob.constant_count}")

    # List blob names
    for blob_name in blob.blobs.keys():
        print(f"Blob: {blob_name}, position: 0x{blob.blobs[blob_name].position:08X}, size: {blob.blobs[blob_name].size} bytes, constant count: {blob.blobs[blob_name].constant_count}")
    
    # Get the __main__ blob and print its constants
    blob = blob.get("__main__")
    print(f"Blob name: {blob.name}, size: {blob.size} bytes, position: 0x{blob.position:08X}, constant count: {blob.constant_count}")
    for constant in blob.constants:
        print(f"  {constant}")

    

if __name__ == '__main__':
    main()
