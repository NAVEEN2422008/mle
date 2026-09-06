"""Lightweight pure-python FITS BINTABLE reader without native C extension dependencies."""
from __future__ import annotations

import io
import struct
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd


def parse_fits_header(stream: io.BytesIO) -> Tuple[Dict[str, Any], int]:
    """Parse 2880-byte header blocks until END card is reached."""
    header: Dict[str, Any] = {}
    bytes_read = 0
    while True:
        block = stream.read(2880)
        if not block or len(block) < 2880:
            break
        bytes_read += 2880
        # 36 cards per block, 80 chars each
        for i in range(0, 2880, 80):
            card = block[i:i+80].decode('ascii', errors='ignore')
            key = card[:8].strip()
            if key == 'END':
                return header, bytes_read
            if '=' in card:
                val_comment = card[8:].split('/', 1)
                val_part = val_comment[0].replace('=', '').strip()
                # parse value
                if val_part.startswith("'"):
                    val = val_part.strip("'").strip()
                elif val_part in ('T', 'F'):
                    val = (val_part == 'T')
                else:
                    try:
                        val = int(val_part)
                    except ValueError:
                        try:
                            val = float(val_part)
                        except ValueError:
                            val = val_part
                header[key] = val
    return header, bytes_read


def read_bintable_hdu(stream: io.BytesIO, header: Dict[str, Any]) -> pd.DataFrame:
    """Parse binary table data block defined by header."""
    naxis1 = header.get('NAXIS1', 0)  # bytes per row
    naxis2 = header.get('NAXIS2', 0)  # number of rows
    tfields = header.get('TFIELDS', 0)
    
    col_names = []
    col_formats = []
    
    # Format mapping for FITS BINTABLE (Big-Endian)
    # D: float64 (>f8), E: float32 (>f4), J: int32 (>i4), I: int16 (>i2), K: int64 (>i8), A: char/string
    dtype_list = []
    for i in range(1, tfields + 1):
        name = header.get(f'TTYPE{i}', f'COL{i}').strip()
        tform = str(header.get(f'TFORM{i}', '1D')).strip()
        col_names.append(name)
        
        # parse repeat count and format char
        fmt_char = tform[-1]
        count = int(tform[:-1]) if len(tform) > 1 else 1
        
        if fmt_char == 'D':
            dt = f'>{count}f8' if count > 1 else '>f8'
        elif fmt_char == 'E':
            dt = f'>{count}f4' if count > 1 else '>f4'
        elif fmt_char == 'J':
            dt = f'>{count}i4' if count > 1 else '>i4'
        elif fmt_char == 'I':
            dt = f'>{count}i2' if count > 2 else '>i2'
        elif fmt_char == 'K':
            dt = f'>{count}i8' if count > 1 else '>i8'
        elif fmt_char == 'A':
            dt = f'|S{count}'
        elif fmt_char == 'B':
            dt = f'|u1'
        elif fmt_char == 'L':
            dt = f'|b1'
        else:
            dt = f'>{count}f8' if count > 1 else '>f8'
            
        dtype_list.append((name, dt))
        
    total_data_bytes = naxis1 * naxis2
    padded_data_bytes = ((total_data_bytes + 2879) // 2880) * 2880
    
    data_raw = stream.read(padded_data_bytes)
    data_actual = data_raw[:total_data_bytes]
    
    if len(data_actual) < total_data_bytes or naxis2 == 0:
        return pd.DataFrame(columns=col_names)
        
    np_dt = np.dtype(dtype_list)
    arr = np.frombuffer(data_actual, dtype=np_dt, count=naxis2)
    
    df_dict = {}
    for name in col_names:
        val = arr[name]
        # convert big-endian to native endianness for pandas/numpy
        if val.dtype.byteorder not in ('=', '|'):
            val = val.astype(val.dtype.newbyteorder('='))
        df_dict[name] = val
        
    return pd.DataFrame(df_dict)


def read_all_hdus(raw_bytes: bytes) -> List[Tuple[Dict[str, Any], Optional[pd.DataFrame]]]:
    """Read all HDUs from raw FITS bytes."""
    stream = io.BytesIO(raw_bytes)
    hdus = []
    while stream.tell() < len(raw_bytes):
        header, _ = parse_fits_header(stream)
        if not header:
            break
        xtension = header.get('XTENSION', '').strip()
        if xtension in ('BINTABLE', 'TABLE'):
            df = read_bintable_hdu(stream, header)
            hdus.append((header, df))
        else:
            # Skip primary or image data array if present
            naxis = header.get('NAXIS', 0)
            bitpix = header.get('BITPIX', 8)
            data_bytes = 0
            if naxis > 0:
                data_size = 1
                for ax in range(1, naxis + 1):
                    data_size *= header.get(f'NAXIS{ax}', 1)
                data_bytes = data_size * abs(bitpix) // 8
                padded = ((data_bytes + 2879) // 2880) * 2880
                stream.seek(padded, io.SEEK_CUR)
            hdus.append((header, None))
    return hdus
