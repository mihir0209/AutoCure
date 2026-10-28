import ipaddress
import urllib.parse

def validate_destination_ip(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    if not host:
        raise PermissionError("SSRF blocked: missing hostname")

    # Clean IPv6 brackets if present
    clean_host = host.strip("[]")

    try:
        ip = ipaddress.ip_address(clean_host)
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise PermissionError(f"SSRF blocked: IP {ip} is in restricted range")
        # Check IPv4-mapped IPv6
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            mapped = ip.ipv4_mapped
            if mapped.is_loopback or mapped.is_private or mapped.is_link_local or str(mapped) == "169.254.169.254":
                raise PermissionError(f"SSRF blocked: IPv4-mapped address {mapped} is restricted")
    except ValueError:
        pass # Non-IP hostname, will be validated during DNS resolution

    return url
