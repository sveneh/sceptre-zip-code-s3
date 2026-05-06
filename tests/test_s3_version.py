from sceptre.resolvers import Resolver

from resolvers.s3_version import S3Version


class FakeConnectionManager:
    def __init__(self):
        self.calls = []

    def call(self, service, command, kwargs):
        self.calls.append({"service": service, "command": command, "kwargs": kwargs})
        return {"VersionId": "version-123"}


class FakeResolver(Resolver):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def resolve(self):
        return self.value


class StackWithResolvingUserData:
    def __init__(self, user_data, connection_manager):
        self.name = "test-stack"
        self._sceptre_user_data = user_data
        self.connection_manager = connection_manager

    @property
    def sceptre_user_data(self):
        raise RuntimeError("dictionary changed size during iteration")


def test_resolves_bucket_and_key_from_raw_sceptre_user_data():
    connection_manager = FakeConnectionManager()
    stack = StackWithResolvingUserData(
        {
            "Code": {
                "S3Bucket": FakeResolver("artifact-bucket"),
                "S3Key": "lambda/dns-delegation.zip",
            }
        },
        connection_manager,
    )
    resolver = S3Version(stack=stack)
    stack._sceptre_user_data["Code"]["S3ObjectVersion"] = resolver

    version = resolver.resolve()

    assert version == "version-123"
    assert connection_manager.calls == [
        {
            "service": "s3",
            "command": "head_object",
            "kwargs": {
                "Bucket": "artifact-bucket",
                "Key": "lambda/dns-delegation.zip",
            },
        }
    ]
