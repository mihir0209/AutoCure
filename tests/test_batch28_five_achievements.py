import pytest
from healing.yaml_unsafe_loader_healer import YamlUnsafeLoaderHealer
from healing.xxe_defusedxml_healer import XxeDefusedxmlHealer
from healing.multiprocessing_race_lock_healer import MultiprocessingRaceLockHealer
from healing.eval_exec_ast_defuser import EvalExecAstDefuser
from healing.zip_slip_extraction_healer import safe_extract_archive_member

def test_achievement_1_yaml_unsafe_loader():
    healer = YamlUnsafeLoaderHealer()
    code = "data = yaml.load(user_stream)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "yaml.safe_load(user_stream)" in healed

def test_achievement_2_xxe_defusedxml():
    healer = XxeDefusedxmlHealer()
    code = "import xml.etree.ElementTree as ET"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "defusedxml.ElementTree" in healed

def test_achievement_3_multiprocessing_race():
    healer = MultiprocessingRaceLockHealer()
    code = "def update_shared_state(val): pass"
    healed, count = healer.heal_source(code)
    assert count == 1

def test_achievement_4_eval_exec_defuser():
    healer = EvalExecAstDefuser()
    code = "result = eval(user_input)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "ast.literal_eval(user_input)" in healed

def test_achievement_5_zip_slip_extraction(tmp_path):
    dest_dir = tmp_path / "extract"
    dest_dir.mkdir()

    # Safe relative member
    safe_path = safe_extract_archive_member(str(dest_dir), "images/avatar.png")
    assert str(dest_dir) in safe_path

    # Hostile escape member
    with pytest.raises(PermissionError, match="Zip slip"):
        safe_extract_archive_member(str(dest_dir), "../../etc/shadow")
