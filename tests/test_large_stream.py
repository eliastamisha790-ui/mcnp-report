import tracemalloc

import pytest

from mcnp_report.parser import parse_output


@pytest.mark.slow
def test_100mb_stream_peak_memory_below_512mb(tmp_path):
    source = tmp_path / "large.out"
    block = (" " + "c synthetic coverage line " + "x" * 996 + "\n").encode("ascii")
    with source.open("wb") as stream:
        stream.write(b"          Code Name & Version = MCNP6, 1.0\n")
        stream.write(b"1mcnp     version 6     ld=05/08/13\n")
        stream.write(b"         1-       mode p\n")
        for _ in range(105_000):
            stream.write(block)
        stream.write(b" run terminated when    10000000  particle histories were done.\n")
    assert source.stat().st_size >= 100 * 1024 * 1024
    tracemalloc.start()
    result = parse_output(source)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    try:
        assert result.metadata.nps == 10_000_000
        assert peak < 512 * 1024 * 1024
    finally: result.close()
