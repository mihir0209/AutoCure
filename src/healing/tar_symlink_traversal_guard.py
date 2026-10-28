import tarfile
import os

def safe_extract_tar(tar_path: str, destination_dir: str):
    abs_dest = os.path.realpath(destination_dir)
    with tarfile.open(tar_path, "r") as tar:
        for member in tar.getmembers():
            target_path = os.path.realpath(os.path.join(abs_dest, member.name))
            if os.path.commonpath([abs_dest, target_path]) != abs_dest:
                raise PermissionError(f"Tar slip traversal escape blocked: {member.name}")
            if member.issym() or member.islnk():
                link_target = os.path.realpath(os.path.join(os.path.dirname(target_path), member.linkname))
                if os.path.commonpath([abs_dest, link_target]) != abs_dest:
                    raise PermissionError(f"Tar symlink pointing outside jail blocked: {member.name} -> {member.linkname}")
        tar.extractall(abs_dest)
