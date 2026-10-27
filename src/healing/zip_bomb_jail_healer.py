"""
AutoCure Zip Bomb & Decompression Quota Jail Healer.
Validates total uncompressed size and compression ratios before extraction.
"""
import zipfile

def safe_extractall_zip(zip_path: str, extract_dir: str, max_size_mb: int = 100, max_ratio: int = 100):
    total_uncompressed = 0
    with zipfile.ZipFile(zip_path, 'r') as z:
        for info in z.infolist():
            total_uncompressed += info.file_size
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > max_ratio:
                    raise PermissionError(f"Zip bomb detected: compression ratio {ratio:.1f} exceeds {max_ratio}")
        if total_uncompressed > (max_size_mb * 1024 * 1024):
            raise PermissionError(f"Zip bomb detected: uncompressed size {total_uncompressed} exceeds {max_size_mb}MB")
        z.extractall(extract_dir)
