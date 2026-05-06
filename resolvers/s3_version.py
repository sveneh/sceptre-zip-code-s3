from sceptre.resolvers import Resolver


class S3Version(Resolver):
    NAME = "s3_version"

    def __init__(self, *args, **kwargs):
        super(S3Version, self).__init__(*args, **kwargs)

    def resolve(self):
        if self.argument:
            s3_bucket, s3_key = self.argument.split("/", 1)
            self.logger.debug(
                "[{}] S3 bucket/key parsed from the argument".format(self.NAME)
            )
        else:
            code = self._get_code_from_raw_sceptre_user_data()
            if code.get("S3Bucket") and code.get("S3Key"):
                s3_bucket, s3_key = [code.get("S3Bucket"), code.get("S3Key")]
            else:
                raise Exception(
                    "S3 bucket/key could not be parsed nor from the argument, neither from sceptre_user_data['Code']"
                )
            self.logger.debug(
                "[{}] S3 bucket/key parsed from sceptre_user_data['Code']".format(
                    self.NAME
                )
            )

        s3_bucket = self._resolve_value(s3_bucket)
        s3_key = self._resolve_value(s3_key)

        # Sceptre v4 provides connection_manager on the stack; fall back if not set on self
        connection_manager = getattr(self, "connection_manager", None) or getattr(self.stack, "connection_manager")

        result = connection_manager.call(
            service="s3",
            command="head_object",
            kwargs={"Bucket": s3_bucket, "Key": s3_key},
        )

        version_id = result.get("VersionId")

        self.logger.debug(
            "[{}] object s3://{}/{} latest version: {}".format(
                self.NAME, s3_bucket, s3_key, version_id
            )
        )

        return version_id

    def _get_code_from_raw_sceptre_user_data(self):
        stack_user_data = {}
        if getattr(self, "stack", None):
            stack_user_data = getattr(self.stack, "_sceptre_user_data", None) or {}
        return stack_user_data.get("Code", {})

    def _resolve_value(self, value):
        if isinstance(value, Resolver):
            value = value.resolve()
        return value
