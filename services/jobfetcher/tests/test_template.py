from pathlib import Path

import pytest
import yaml

TEMPLATE = Path(__file__).parents[1] / "template.yaml"


class _CfnLoader(yaml.SafeLoader):
    pass


def _ignore_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_CfnLoader.add_multi_constructor("!", _ignore_tag)


@pytest.fixture(scope="module")
def template():
    return yaml.load(TEMPLATE.read_text(encoding="utf-8"), Loader=_CfnLoader)


def test_is_a_sam_template(template):
    assert template["Transform"] == "AWS::Serverless-2016-10-31"


def test_function_defaults_match_the_spec(template):
    defaults = template["Globals"]["Function"]
    assert defaults["Runtime"] == "python3.13"
    assert defaults["Architectures"] == ["x86_64"]
    assert defaults["MemorySize"] == 512
    assert defaults["Timeout"] == 120


def test_function_wiring(template):
    props = template["Resources"]["JobFetcherFunction"]["Properties"]
    assert props["CodeUri"] == "src/"
    assert props["Handler"] == "jobfetcher.handler.lambda_handler"
    assert props["Environment"]["Variables"]["BUCKET_NAME"] == "JobsBucket"


def test_runtime_role_can_only_put_objects_under_jobs(template):
    props = template["Resources"]["JobFetcherFunction"]["Properties"]
    statements = [s for policy in props["Policies"] for s in policy["Statement"]]
    assert len(statements) == 1
    statement = statements[0]
    assert statement["Effect"] == "Allow"
    assert statement["Action"] == "s3:PutObject"
    assert statement["Resource"].endswith("/jobs/*")


def test_function_runs_on_a_daily_schedule(template):
    events = template["Resources"]["JobFetcherFunction"]["Properties"]["Events"]
    schedules = [e for e in events.values() if e["Type"] == "Schedule"]
    assert len(schedules) == 1
    assert schedules[0]["Properties"]["Schedule"].startswith("cron(")


def test_bucket_is_private_encrypted_and_expires_dated_objects_only(template):
    props = template["Resources"]["JobsBucket"]["Properties"]
    assert props["PublicAccessBlockConfiguration"] == {
        "BlockPublicAcls": True,
        "BlockPublicPolicy": True,
        "IgnorePublicAcls": True,
        "RestrictPublicBuckets": True,
    }
    encryption = props["BucketEncryption"]["ServerSideEncryptionConfiguration"][0]
    assert encryption["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"
    rule = props["LifecycleConfiguration"]["Rules"][0]
    assert rule["Status"] == "Enabled"
    assert rule["Prefix"] == "jobs/20"  # dated objects only, never latest.json
    assert rule["ExpirationInDays"] == 30


def test_outputs_expose_bucket_and_function_names(template):
    assert set(template["Outputs"]) == {"BucketName", "FunctionName"}
