from aibutton.ble_peripheral import chunk_utf8


def test_empty_string():
    assert chunk_utf8("", 180) == []


def test_fits_one_chunk():
    assert chunk_utf8("a" * 180, 180) == [b"a" * 180]


def test_one_byte_over_splits():
    chunks = chunk_utf8("a" * 181, 180)
    assert [len(c) for c in chunks] == [180, 1]


def test_multibyte_chars_never_split():
    text = "é" * 100  # 2 bytes each
    chunks = chunk_utf8(text, 5)
    for c in chunks:
        c.decode("utf-8")  # raises if a char was split
        assert len(c) <= 5
    assert b"".join(chunks).decode("utf-8") == text


def test_emoji_never_split():
    text = "🎵" * 50  # 4 bytes each
    chunks = chunk_utf8(text, 5)
    for c in chunks:
        c.decode("utf-8")
        assert len(c) <= 5
    assert b"".join(chunks) == text.encode("utf-8")


def test_reassembly_matches_original():
    text = "status OK — 機械 is happy 🎉 " * 40
    assert b"".join(chunk_utf8(text, 180)).decode("utf-8") == text
