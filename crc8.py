def crc8(data: bytes) -> int:
    """
    Calculates CRC-8 checksum using polynomial X^8 + X^2 + X + 1 (0x07).
    Matches the CRC-8 implementation required by the MEAN WELL LAD series.
    """
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x07
            else:
                crc <<= 1
            crc &= 0xFF
    return crc


def verify_crc8(data: bytes, expected_crc: int) -> bool:
    """
    Verifies that the CRC-8 of the data matches the expected CRC value.
    """
    return crc8(data) == expected_crc
