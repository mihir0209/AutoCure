import pytest
from healing.celementtree_entity_healer import CElementTreeEntityHealer
from healing.vault_credential_healer import heal_hardcoded_aws_credentials
from healing.asyncio_shield_leak_healer import AsyncioShieldLeakHealer
from healing.pyyaml_loader_healer import PyYamlLoaderHealer
from healing.jinja2_autoescape_healer import Jinja2AutoescapeHealer

def test_achievement_1_celementtree_healer():
    healer = CElementTreeEntityHealer()
    code = "import xml.etree.cElementTree as ET"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "defusedxml.ElementTree" in healed

def test_achievement_2_vault_credentials():
    code = 's3 = boto3.client("s3", aws_access_key_id="AKIAIOSFODNN7EXAMPLE")'
    healed = heal_hardcoded_aws_credentials(code)
    assert "AKIAIOSFODNN7EXAMPLE" not in healed
    assert 'os.environ.get("AWS_ACCESS_KEY_ID")' in healed

def test_achievement_3_asyncio_shield_healer():
    healer = AsyncioShieldLeakHealer()
    code = "res = await asyncio.shield(task)"
    healed, count = healer.heal_source(code)
    assert count == 1

def test_achievement_4_pyyaml_loader():
    healer = PyYamlLoaderHealer()
    code = "doc = yaml.load(f, Loader=yaml.FullLoader)"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "yaml.SafeLoader" in healed

def test_achievement_5_jinja2_autoescape():
    healer = Jinja2AutoescapeHealer()
    code = "env = Environment(loader=FileSystemLoader('templates'))"
    healed, count = healer.heal_source(code)
    assert count == 1
    assert "autoescape=True" in healed
