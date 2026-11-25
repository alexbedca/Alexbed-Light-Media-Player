"""Mark the second El Torito boot entry of an ISO made by VMware's old mkisofs as UEFI.

That mkisofs writes the EFI image (boot/grub/efi.img) as a second entry with no section header, so
firmware never sees it. This adds the header (platform 0xEF = EFI). Usage: python -I patch_eltorito.py <iso>
"""
import struct
import sys

path = sys.argv[1]
with open(path, "r+b") as f:
    f.seek(17 * 2048)
    brvd = f.read(2048)
    assert brvd[1:6] == b"CD001" and brvd[7:30].startswith(b"EL TORITO")
    catalog_lba = struct.unpack("<I", brvd[0x47:0x4B])[0]
    f.seek(catalog_lba * 2048)
    cat = bytearray(f.read(2048))
    efi_entry = bytes(cat[64:96])
    assert efi_entry[0] == 0x88 and cat[96:128] == bytes(32), "unexpected boot catalogue layout"
    header = bytearray(32)
    header[0] = 0x91                       # last section header
    header[1] = 0xEF                       # platform: EFI
    header[2:4] = struct.pack("<H", 1)     # one entry follows
    cat[64:96] = header
    cat[96:128] = efi_entry
    f.seek(catalog_lba * 2048)
    f.write(cat)
    for i in range(0, 128, 32):
        print(i, cat[i:i + 12].hex())
