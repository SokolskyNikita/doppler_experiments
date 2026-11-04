"""(Named so the repo-wide pytest skips it: it needs this folder's environment.) The synthesized stack, checked before any deploy: the rules the README promises and the outputs runs reads."""
import json
import re
import sys
from pathlib import Path

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.argv = ["app.py"]     # app.py synthesizes on import; give it a clean argv


def template() -> Template:
    import app
    stack = app.FleetStack(cdk.App(), "Test", env=cdk.Environment(account="123456789012", region=app.REGION))
    return Template.from_stack(stack)


T = template()


def test_the_bucket_is_private_versioned_and_kept():
    T.has_resource("AWS::S3::Bucket", {"DeletionPolicy": "Retain", "Properties": Match.object_like({
        "PublicAccessBlockConfiguration": {"BlockPublicAcls": True, "BlockPublicPolicy": True,
                                           "IgnorePublicAcls": True, "RestrictPublicBuckets": True},
        "VersioningConfiguration": {"Status": "Enabled"}})})
    policy = json.dumps(T.find_resources("AWS::S3::BucketPolicy"))
    assert '"aws:SecureTransport": "false"' in policy


def test_the_box_role_can_never_delete_and_writes_only_its_prefixes():
    docs = [r["Properties"]["PolicyDocument"] for r in T.find_resources("AWS::IAM::Policy").values()]
    actions, put_prefixes = set(), set()
    for d in docs:
        for st in d["Statement"]:
            acts = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
            actions |= set(acts)
            if "s3:PutObject" in acts:
                put_prefixes.add(re.search(r'"/([^"]*)\*"', json.dumps(st["Resource"])).group(1))
    assert not [a for a in actions if "Delete" in a]
    assert put_prefixes == {"jobs/", "runs/", "cache-deltas/", "data/raw/", "data/derived/"}


def test_no_inbound_traffic_and_imdsv2_with_tags_on_every_job_box():
    for sg in T.find_resources("AWS::EC2::SecurityGroup").values():
        assert not sg["Properties"].get("SecurityGroupIngress")
    lts = [r for r in T.find_resources("AWS::EC2::LaunchTemplate").values()
           if r["Properties"].get("LaunchTemplateName", "").startswith("dopplertrack-job-")]
    assert len(lts) == 2
    for lt in lts:
        d = lt["Properties"]["LaunchTemplateData"]
        assert d["MetadataOptions"] == {"HttpTokens": "required", "InstanceMetadataTags": "enabled"}
        assert d["InstanceInitiatedShutdownBehavior"] == "terminate"


def test_every_output_runs_reads_exists():
    src = (HERE / "runs.py").read_text()
    used = set(re.findall(r'out(?:puts\(\))?\["(\w+)"\]', src)) | {f"Template{a.capitalize()}" for a in ("arm64", "amd64")}
    assert used <= set(T.to_json()["Outputs"]), used - set(T.to_json()["Outputs"])


def test_the_user_data_has_no_unfilled_placeholder():
    for lt in T.find_resources("AWS::EC2::LaunchTemplate").values():
        ud = json.dumps(lt["Properties"]["LaunchTemplateData"].get("UserData", ""))
        assert "@@" not in ud
