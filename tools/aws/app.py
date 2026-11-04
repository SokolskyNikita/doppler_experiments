"""The CDK app: one stack, DopplertrackFleet, in us-west-2. `cdk deploy` from tools/aws brings it up.

What it holds:
- the bucket: the data root (data/), the seeded caches (cache/), the tools a box installs (tools/), job specs
  and code (jobs/), run folders (runs/) and the cache entries jobs add (cache-deltas/). Private, public
  access blocked, TLS only, versioned (a replaced object is kept 30 days), kept when the stack is deleted;
- a VPC with a public subnet in each of the four AZs, no NAT, and a free S3 gateway endpoint;
- a security group with no inbound rules: the boxes are reached through Systems Manager only;
- the boxes' role: Systems Manager, read on the bucket, and writes (no deletes) under jobs/, runs/,
  cache-deltas/, data/raw/ and data/derived/, so a job can't touch cache/ or tools/;
- a launch template per architecture (arm64 for c8g, c8gd, c7g; amd64 for c7a) on the stock Ubuntu 24.04
  image, whose user data is box/bootstrap.sh; `runs launch` starts an instant EC2 Fleet over both;
- the dev box, a c8g.2xlarge on demand, stopped by an alarm after 30 min below 5 % CPU."""
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cwa
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

HERE = Path(__file__).parent
REGION = "us-west-2"        # the home region: the bucket and the dev box
# where job boxes can run, nearest first, with the AZs that offer the fleet's families (c8gd: us-west-2, us-east-2)
REGIONS = {"us-west-2": ["us-west-2a", "us-west-2b", "us-west-2c", "us-west-2d"],
           "us-west-1": ["us-west-1a", "us-west-1c"],
           "us-east-2": ["us-east-2a", "us-east-2b", "us-east-2c"]}
UBUNTU = "/aws/service/canonical/ubuntu/server/24.04/stable/current/{arch}/hvm/ebs-gp3/ami-id"
JOB_ROOT_GB = 200
DEV_TYPE = "c8g.2xlarge"
DEV_ROOT_GB = 300


def user_data(name: str, bucket: s3.IBucket) -> ec2.UserData:
    text = (HERE / "box" / name).read_text().replace("@@BUCKET@@", bucket.bucket_name)
    return ec2.UserData.custom(text.replace("@@BUCKET_REGION@@", REGION))


def root_volume(gb: int, throughput: int | None = 500) -> ec2.BlockDevice:
    """gp3 with 6000 IOPS; CDK can set the throughput only through a launch template."""
    return ec2.BlockDevice(device_name="/dev/sda1", volume=ec2.BlockDeviceVolume.ebs(
        gb, volume_type=ec2.EbsDeviceVolumeType.GP3, iops=6000, throughput=throughput, encrypted=True,
        delete_on_termination=True))


class FleetStack(cdk.Stack):
    """The home stack (bucket, dev box, job boxes) in REGION, or a compute-only one elsewhere: the same VPC,
    role, launch templates and FIS role, its boxes using the home bucket across regions."""

    def __init__(self, scope: Construct, cid: str, home: bool = True, **kw):
        super().__init__(scope, cid, **kw)
        if not home:
            self.compute(s3.Bucket.from_bucket_name(self, "Data", f"dopplertrack-{self.account}-{REGION}"), None)
            return
        bucket = s3.Bucket(
            self, "Data", bucket_name=f"dopplertrack-{self.account}-{self.region}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True, object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            removal_policy=cdk.RemovalPolicy.RETAIN, versioned=True,
            lifecycle_rules=[s3.LifecycleRule(abort_incomplete_multipart_upload_after=cdk.Duration.days(2),
                                              noncurrent_version_expiration=cdk.Duration.days(30)),
                             s3.LifecycleRule(prefix="jobs/", expiration=cdk.Duration.days(60)),
                             s3.LifecycleRule(prefix="dev/", expiration=cdk.Duration.days(7))])

        self.compute(bucket, bucket)

    def compute(self, bucket: s3.IBucket, home_bucket: s3.Bucket | None) -> None:
        vpc = ec2.Vpc(
            self, "Vpc", availability_zones=REGIONS[self.region], nat_gateways=0, ip_addresses=ec2.IpAddresses.cidr("10.42.0.0/16"),
            subnet_configuration=[ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC,
                                                          cidr_mask=20)],
            gateway_endpoints={"S3": ec2.GatewayVpcEndpointOptions(service=ec2.GatewayVpcEndpointAwsService.S3)})
        sg = ec2.SecurityGroup(self, "Boxes", vpc=vpc, allow_all_outbound=True,
                               description="dopplertrack boxes: no inbound, reached through Systems Manager")

        role = iam.Role(self, "BoxRole", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
                        managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name(
                            "AmazonSSMManagedInstanceCore")])
        bucket.grant_read(role)
        # data/raw/ and data/derived/ too, so a job can fetch a raw file from its source or build a derived one;
        # the role has no delete, and the bucket keeps every replaced version for 30 days
        for prefix in ("jobs/*", "runs/*", "cache-deltas/*", "data/raw/*", "data/derived/*"):
            bucket.grant_put(role, prefix)

        templates = {}
        for arch in ("arm64", "amd64"):
            templates[arch] = ec2.LaunchTemplate(
                self, f"Job-{arch}", launch_template_name=f"dopplertrack-job-{arch}",
                machine_image=ec2.MachineImage.from_ssm_parameter(UBUNTU.format(arch=arch)),
                role=role, security_group=sg, user_data=user_data("bootstrap.sh", bucket),
                instance_initiated_shutdown_behavior=ec2.InstanceInitiatedShutdownBehavior.TERMINATE,
                require_imdsv2=True, instance_metadata_tags=True, block_devices=[root_volume(JOB_ROOT_GB)])

        fis = iam.Role(self, "FisRole", assumed_by=iam.ServicePrincipal("fis.amazonaws.com"))
        fis.add_to_policy(iam.PolicyStatement(actions=["ec2:SendSpotInstanceInterruptions"], resources=["*"],
                                              conditions={"StringEquals": {"aws:ResourceTag/project": "dopplertrack"}}))
        fis.add_to_policy(iam.PolicyStatement(actions=["ec2:DescribeInstances"], resources=["*"]))
        out = {"Bucket": bucket.bucket_name, "FisRoleArn": fis.role_arn, "SecurityGroup": sg.security_group_id,
               "Subnets": ",".join(s.subnet_id for s in vpc.public_subnets),
               "TemplateArm64": templates["arm64"].launch_template_id,
               "TemplateAmd64": templates["amd64"].launch_template_id}
        if home_bucket is not None:
            out["DevBoxId"] = self.dev_box(vpc, role, sg, bucket)
        for k, v in out.items():
            cdk.CfnOutput(self, k, value=v)

    def dev_box(self, vpc, role, sg, bucket) -> str:
        dev = ec2.Instance(
            self, "DevBox", instance_name="dopplertrack-dev", instance_type=ec2.InstanceType(DEV_TYPE),
            machine_image=ec2.MachineImage.from_ssm_parameter(UBUNTU.format(arch="arm64")), vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC, availability_zones=["us-west-2b"]),
            role=role, security_group=sg, user_data=user_data("devbox.sh", bucket), require_imdsv2=True,
            block_devices=[root_volume(DEV_ROOT_GB, None)])
        idle = cw.Alarm(
            self, "DevBoxIdle", alarm_name="dopplertrack-dev-idle", threshold=5, evaluation_periods=6,
            comparison_operator=cw.ComparisonOperator.LESS_THAN_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            alarm_description="stops the dev box after 30 min with no 5-minute CPU maximum above 5 %",
            metric=cw.Metric(namespace="AWS/EC2", metric_name="CPUUtilization",
                             dimensions_map={"InstanceId": dev.instance_id}, statistic="Maximum",
                             period=cdk.Duration.minutes(5)))
        idle.add_alarm_action(cwa.Ec2Action(cwa.Ec2InstanceAction.STOP))

        return dev.instance_id


app = cdk.App()
for region in REGIONS:     # the same stack name in every region; `cdk deploy --all` deploys them all
    stack = FleetStack(app, "DopplertrackFleet" if region == REGION else f"DopplertrackFleet-{region}",
                       home=region == REGION, stack_name="DopplertrackFleet", env=cdk.Environment(region=region))
    cdk.Tags.of(stack).add("project", "dopplertrack")
app.synth()
