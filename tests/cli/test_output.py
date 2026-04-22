from openagentmesh._models import CatalogEntry
from openagentmesh.cli._output import as_json, table


def test_table_header_and_row_formatting():
    out = table([["foo", "1"], ["longer", "22"]], ["name", "n"])
    assert out.splitlines()[0].startswith("name")
    assert "longer" in out
    assert "22" in out


def test_table_empty_rows_shows_marker():
    out = table([], ["a", "b"])
    assert "(empty)" in out


def test_json_handles_pydantic_model():
    entry = CatalogEntry(
        name="agent", description="desc",
        streaming=False, invocable=True, tags=["x"],
    )
    out = as_json(entry)
    assert '"name": "agent"' in out


def test_json_handles_pydantic_list():
    entry = CatalogEntry(
        name="agent", description="d",
        streaming=False, invocable=True, tags=[],
    )
    out = as_json([entry])
    assert '"name": "agent"' in out


def test_json_handles_plain_dict():
    out = as_json({"b": 1, "a": 2})
    assert '"a": 2' in out
    assert out.index('"a"') < out.index('"b"')  # sort_keys
