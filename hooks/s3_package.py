import hashlib, os, subprocess, zipfile
from base64 import b64encode
from subprocess import DEVNULL
from io import BytesIO as BufferIO
from sceptre.hooks import Hook
from sceptre.resolvers import Resolver
from botocore.exceptions import ClientError
from datetime import datetime
from shutil import rmtree

compression = zipfile.ZIP_DEFLATED


class S3Package(Hook):
    NAME = "s3_package"
    TARGET = "dist"
    DELIMITER = "^^"

    def __init__(self, *args, **kwargs):
        super(S3Package, self).__init__(*args, **kwargs)

    def run(self):
        if self.DELIMITER in self.argument:
            fn_root_dir, s3_object = self.argument.split(self.DELIMITER, 1)
            s3_bucket, s3_key = s3_object.split("/", 1)
            self.logger.debug(
                f"[{self.NAME}] S3 bucket/key parsed from the argument: {s3_bucket}/{s3_key}"
            )
        else:
            # Sceptre v4: data lives on self.stack.sceptre_user_data
            # v2/v3: some custom hooks used self.stack_config; keep a soft fallback.
            stack_user_data = None
            if getattr(self, "stack", None):
                stack_user_data = getattr(self.stack, "sceptre_user_data", None)
            if not stack_user_data and getattr(self, "stack_config", None):
                stack_user_data = self.stack_config.get("sceptre_user_data")

            if stack_user_data and "Code" in stack_user_data:
                code = stack_user_data.get("Code", {})
            else:
                code = {}

            if code.get("S3Bucket") and code.get("S3Key"):
                fn_root_dir, s3_bucket, s3_key = [
                    self.argument,
                    code.get("S3Bucket"),
                    code.get("S3Key"),
                ]
                self.logger.debug(
                    f"[{self.NAME}] S3 bucket/key parsed from sceptre_user_data['Code']: {s3_bucket}/{s3_key}"
                )
            else:
                raise Exception(
                    "S3 bucket/key could not be parsed nor from the argument, neither from sceptre_user_data['Code']"
                )

        if isinstance(s3_bucket, Resolver):
            s3_bucket = s3_bucket.resolve()
            self.logger.debug(f"[{self.NAME}] resolved S3 bucket value to {s3_bucket}")

        if isinstance(s3_key, Resolver):
            s3_key = s3_key.resolve()
            self.logger.debug(f"[{self.NAME}] resolved S3 key value to {s3_key}")

        fn_dist_dir = os.path.join(fn_root_dir, self.TARGET)

        command = f"make -C {fn_root_dir}"

        self.logger.info(f"Making dependencies with '{command}' command, output hidden.")

        p = subprocess.Popen([command], shell=True, stdout=DEVNULL, stderr=DEVNULL)
        p.wait()

        if p.returncode != 0:
            raise Exception("Failed to make dependencies, debug command manually.")

        self.logger.debug(
            f"[{self.NAME}] reading ALL files from {fn_dist_dir}/ directory"
        )

        files = sorted(
            [
                os.path.join(root[len(fn_dist_dir) + 1 :], file)
                for root, _, files in os.walk(fn_dist_dir)
                for file in files
            ]
        )

        buffer = BufferIO()

        # static timestamp to keep same ZIP checksum on same files
        static_ts = int(datetime(2018, 1, 1).strftime("%s"))

        with zipfile.ZipFile(buffer, mode="w", compression=compression) as f:
            for file in files:
                real_file = os.path.join(fn_dist_dir, file)
                self.logger.debug(f"[{self.NAME}] zipping file {real_file}")
                os.utime(real_file, (static_ts, static_ts))
                f.write(real_file, arcname=file)

        rmtree(fn_dist_dir)

        buffer.seek(0)
        content = buffer.read()

        md5 = hashlib.new("md5")
        md5.update(content)

        # Sceptre v4 provides connection_manager on the stack; fall back if not set on self
        connection_manager = getattr(self, "connection_manager", None) or getattr(self.stack, "connection_manager")

        try:
            connection_manager.call(
                service="s3",
                command="head_object",
                kwargs={
                    "Bucket": s3_bucket,
                    "Key": s3_key,
                    "IfMatch": f"\"{md5.hexdigest()}\"",
                },
            )

            self.logger.info(f"[{self.NAME}] skip packaging {fn_dist_dir} - no changes detected")
        except ClientError as e:
            if e.response["Error"]["Code"] not in ["404", "412"]:
                raise e

            self.logger.info(f"[{self.NAME}] uploading {fn_dist_dir} to s3://{s3_bucket}/{s3_key}")

            result = connection_manager.call(
                service="s3",
                command="put_object",
                kwargs={
                    "Bucket": s3_bucket,
                    "Key": s3_key,
                    "Body": content,
                    "ContentMD5": b64encode(md5.digest()).strip().decode("utf-8"),
                },
            )

            self.logger.debug(
                f"[{self.NAME}] object s3://{s3_bucket}/{s3_key} new version: {result.get('VersionId')}"
            )
