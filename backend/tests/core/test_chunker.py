import json

from app.core.chunker import content_registry_types, enrich_object


def test_content_registry_excludes_engine_internal(monkeypatch):
    from app.core import chunker

    # ? tier rule: imports file -> community_example; engine _functions -> authoritative
    def fake_tier(rec, repo_dirs):
        return "community_example" if rec["repo"] == "imports_source" else "authoritative"

    monkeypatch.setattr(chunker, "tier_for_record", fake_tier)
    objects = [
        {"repo": "imports_source", "file": "a.js", "object_type": "SpellsList"},
        {"repo": "mpmb_source", "file": "_functions/F.js", "object_type": "SetUnitDecimals_Dialog"},
    ]
    types = content_registry_types(objects, repo_dirs={})
    assert "SpellsList" in types
    assert "SetUnitDecimals_Dialog" not in types


def test_enrich_spell_pulls_level_and_school():
    content = 'SpellsList["fireball"] = { name : "Fireball", level : 3, school : "Evocation" }'
    meta = enrich_object("SpellsList", content, "fireball")
    assert meta["object_type"] == "SpellsList"
    assert meta["object_key"] == "fireball"
    assert meta["spell_level"] == 3
    assert meta["spell_school"] == "Evocation"
    assert meta["display_name"] == "Fireball"


def test_chunk_objects_slices_by_span(tmp_path, monkeypatch):
    from app.core import chunker

    f = tmp_path / "imp.js"
    f.write_text('x;\nSpellsList["a"] = {\n  name : "A"\n};\n', encoding="utf-8")
    repo_dirs = {"imports_source": tmp_path}
    monkeypatch.setattr(chunker, "detect_edition", lambda *a, **k: "2014")
    monkeypatch.setattr(chunker, "determine_source_tier", lambda *a, **k: "community_example")
    objects = [
        {
            "repo": "imports_source",
            "file": "imp.js",
            "object_type": "SpellsList",
            "object_key": "a",
            "line": 2,
            "end_line": 4,
            "assignment_kind": "bracket_object",
        }
    ]
    chunks = chunker.chunk_objects(objects, content_types={"SpellsList"}, repo_dirs=repo_dirs)
    assert len(chunks) == 1
    assert chunks[0].chunk_type == "object_literal"
    assert chunks[0].start_line == 2 and chunks[0].end_line == 4
    assert 'SpellsList["a"]' in chunks[0].content and "name" in chunks[0].content


def test_chunk_objects_skips_minified_bundles(tmp_path, monkeypatch):
    from app.core import chunker

    # ! the WotC min.js bundle is one giant line; chunking it produces multi-MB chunks -> OOM
    f = tmp_path / "all_WotC_pub+UA.min.js"
    f.write_text('SpellsList["a"] = {name:"A"};', encoding="utf-8")
    monkeypatch.setattr(chunker, "detect_edition", lambda *a, **k: "2014")
    monkeypatch.setattr(chunker, "determine_source_tier", lambda *a, **k: "official_example")
    objects = [
        {
            "repo": "imports_source",
            "file": "all_WotC_pub+UA.min.js",
            "object_type": "SpellsList",
            "object_key": "a",
            "line": 1,
            "end_line": 1,
            "assignment_kind": "bracket_object",
        }
    ]
    chunks = chunker.chunk_objects(objects, content_types={"SpellsList"}, repo_dirs={"imports_source": tmp_path})
    assert chunks == []


def test_chunk_add_calls_emits_function_call(tmp_path, monkeypatch):
    from app.core import chunker

    f = tmp_path / "sub.js"
    f.write_text('AddSubClass("fighter", "knight", {\n  subname : "Knight"\n});\n', encoding="utf-8")
    monkeypatch.setattr(chunker, "detect_edition", lambda *a, **k: "2014")
    monkeypatch.setattr(chunker, "determine_source_tier", lambda *a, **k: "community_example")
    add_calls = [
        {
            "repo": "imports_source",
            "file": "sub.js",
            "function_name": "AddSubClass",
            "line": 1,
            "end_line": 3,
            "mapped": True,
        }
    ]
    chunks = chunker.chunk_add_calls(add_calls, repo_dirs={"imports_source": tmp_path})
    assert chunks[0].chunk_type == "function_call"
    assert chunks[0].metadata["parent_class"] == "fighter"
    assert chunks[0].metadata["object_key"] == "knight"
    assert chunks[0].metadata["display_name"] == "Knight"


def test_chunk_functions_engine_only_with_jsdoc(tmp_path, monkeypatch):
    from app.core import chunker

    d = tmp_path / "_functions"
    d.mkdir()
    f = d / "F.js"
    f.write_text("/** doc */\nfunction CreateSpellList(o) {\n  return o;\n}\n", encoding="utf-8")
    monkeypatch.setattr(chunker, "detect_edition", lambda *a, **k: "2014")
    monkeypatch.setattr(chunker, "determine_source_tier", lambda *a, **k: "authoritative")
    functions = [
        {
            "repo": "mpmb_source",
            "file": "_functions/F.js",
            "name": "CreateSpellList",
            "kind": "declaration",
            "line": 2,
            "end_line": 4,
        }
    ]
    chunks = chunker.chunk_functions(functions, repo_dirs={"mpmb_source": tmp_path})
    assert chunks[0].chunk_type == "function_definition"
    assert chunks[0].metadata["function_name"] == "CreateSpellList"
    assert chunks[0].metadata["has_jsdoc"] is True
    assert "/** doc */" in chunks[0].content


def test_extract_syntax_templates_emits_template_attribute():
    from app.core.chunker import extract_syntax_templates

    content = '\tname : "Example",\n\t/* // REQUIRED // TYPE: string USE: the display name */\n'
    chunks = extract_syntax_templates(content, "magic item (MagicItemsList).js", "2014", "authoritative", "mpmb")
    assert chunks
    assert chunks[0].chunk_type == "template_attribute"
    assert chunks[0].metadata["attribute_name"] == "name"
    assert chunks[0].metadata["is_required"] is True
    assert chunks[0].metadata["object_type"] == "MagicItemsList"


def test_run_all_consumes_report(tmp_path, monkeypatch):
    from app.core import chunker

    imp = tmp_path / "imports"
    imp.mkdir()
    (imp / "c.js").write_text(
        'SpellsList["a"] = {\n  name : "A"\n};\nAddSubClass("fighter", "knight", {\n  subname : "K"\n});\n',
        encoding="utf-8",
    )
    eng = tmp_path / "mpmb" / "_functions"
    eng.mkdir(parents=True)
    (eng / "F.js").write_text("function CreateSpellList(o) {\n  return o;\n}\n", encoding="utf-8")

    monkeypatch.setattr(
        chunker, "analyzer_repo_dirs", lambda: {"imports_source": imp, "mpmb_source": tmp_path / "mpmb"}
    )
    # ? isolate from the real syntax-template dirs
    monkeypatch.setattr(chunker.MPMBChunker, "_chunk_syntax_templates", lambda self: [])

    report = {
        "objects": [
            {
                "repo": "imports_source",
                "file": "c.js",
                "object_type": "SpellsList",
                "object_key": "a",
                "line": 1,
                "end_line": 3,
                "assignment_kind": "bracket_object",
            }
        ],
        "add_calls": [
            {
                "repo": "imports_source",
                "file": "c.js",
                "function_name": "AddSubClass",
                "line": 4,
                "end_line": 6,
                "mapped": True,
            }
        ],
        "functions": [
            {
                "repo": "mpmb_source",
                "file": "_functions/F.js",
                "name": "CreateSpellList",
                "kind": "declaration",
                "line": 1,
                "end_line": 3,
            }
        ],
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    out = tmp_path / "out"

    result = chunker.MPMBChunker().run_all(report_path=report_path, output_dir=out)
    by_type = result["stats"]["by_type"]
    assert by_type.get("object_literal") == 1
    assert by_type.get("function_call") == 1
    assert by_type.get("function_definition") == 1
    assert result["chunker_version"] == "2"
    assert (out / "object_literal.json").exists()
