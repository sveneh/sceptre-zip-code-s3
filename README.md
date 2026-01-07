# Sceptre zip-code-s3

Hook and resolver for [Sceptre](https://sceptre.cloudreach.com/latest/) `v4` to package Lambda code on-the-fly and push it to S3. Tested with **Python 3.8+**. Current release: **2.0.0**.

## Overview

Lambda function may consist of several files or may require custom packages,
which do not exist in AWS runtime and must be installed manually before packaging.

Many developers tend to store packaged Zip archive within Git repository.
That may lead to inconsistent deployment, because
such archive has to be recreate, if any source or dependency file has changed.

This important action usually recalled after hours of debugging and tons of redeployments.
Therefore, such archived artifacts should never be checked in, rather packaged and deployed to on-the-fly.

## Getting Started

### Install

```bash
# editable (recommended for local development)
pip install -e /path/to/sceptre-zip-code-s3

# or regular install
pip install /path/to/sceptre-zip-code-s3
```

Requires `sceptre>=4,<5` and Python 3.8+ (declared in `setup.py`).

### Usage (hook + resolver)

Hook to build/zip/upload before create/update:
```yaml
hooks:
  before_create:
    - !s3_package path/to/code^^my-bucket/path/to/code.zip
  before_update:
    - !s3_package path/to/code^^my-bucket/path/to/code.zip
```

Resolver to fetch the latest object version (optional):
```yaml
sceptre_user_data:
  Code:
    S3Bucket: my-bucket
    S3Key: path/to/code.zip
    S3ObjectVersion: !s3_version my-bucket/path/to/code.zip
```

See `config/example/` for complete sample stacks (bucket, role, lambda). To display available commands, run `make` or `make help`.

### Prepare project

* Update `config/config.yaml` file with preferred values:

    ```bash
    $ cp config/config.yaml.dist config/config.yaml
    $ vi config/config.yaml
    ```

### Example walkthrough

- Create artifacts bucket: `sceptre launch-env example/storage`
- Deploy role + lambda: `sceptre launch-env example/serverless`

This builds dependencies, zips code, uploads to S3 if changed, updates the stack, and cleans up the dist directory.

### Test Lambda function from CLI

Find generated function name and region:

```bash
$ LAMBDA=( $(sceptre describe-stack-outputs example/serverless lambda-py2-deps \
    | grep ':lambda:' \
    | awk -F: '{print $NF, $5}') )
```

And then invoke function with JSON payload and parse result file:

```bash
$ aws lambda invoke \
    --invocation-type RequestResponse \
    --function-name "${LAMBDA[0]}" \
    --region "${LAMBDA[1]}" \
    --payload '{"key1":"value-1", "key2":[21, 42], "key3":[{"name":"value-3"}]}' \
    output.txt

$ cat output.txt | xargs echo -e
```

If everything went well, you’ll see the helper output echoed from the Lambda payload.

### Cleanup infrastructure

* Do not forget to cleanup infrastructure after testing:

    ```bash
    $ sceptre delete-env example/serverless
    ```

* If new S3 bucket was created during the test:

    ```bash
    $ sceptre delete-env example/storage
    ```

    If it errors with `You must delete all versions in the bucket`, then:

    ```bash
    $ MY_BUCKET="$(awk '$1 == "artifacts_bucket:" {print $2}' config/config.yaml)"

    $ python -c "import boto3; boto3.resource('s3').Bucket('${MY_BUCKET}').object_versions.delete()"

    $ sceptre delete-env example/storage
    ```

## Under the hood

### Hook definition

`s3_package` hook is template agnostic solution and it has 2 forms of definitions:

* S3 bucket/key auto-discovery:

    This way hook tries to auto-discover `S3Bucket`/`S3Key` values from `sceptre_user_data['Code']` config.

    Template & config must follow [lambda_function.py](./templates/example/lambda_function.py) template convention for `Code` parameter.

    ```yaml
    hooks:
        before_create:
            - !s3_package <path-to-function-root>
        before_update:
            - !s3_package <path-to-function-root>
    ```

* S3 bucket/key passed directly, fallback for custom template:

    ```yaml
    hooks:
        before_create:
            - !s3_package <path-to-function-root>^^<s3_bucket>/<s3_key>
        before_update:
            - !s3_package <path-to-function-root>^^<s3_bucket>/<s3_key>
    ```

### Resolver definition

`Cloudformation` wont detect stack changes, if no `Code.S3ObjectVersion` key is provided and lambda wont be redeployed with updates.

As hook definition, resolver also has **auto-discovery** and **direct** modes.

* S3 bucket/key auto-discovery:

    ```yaml
    sceptre_user_data:
        Code:
            S3Bucket: <s3_bucket>
            S3Key: <s3_key>
            S3ObjectVersion: !s3_version
    ```

* S3 bucket/key passed directly, fallback for custom template:

    ```yaml
    sceptre_user_data:
        BucketName: <s3_bucket>
        ObjectKey: <s3_key>
        ObjectVersion: !s3_version <s3_bucket>/<s3_key>
    ```

* S3 bucket/key names come from another stack:

    ```yaml
    sceptre_user_data:
        Code:
            S3Bucket: !stack_output my-other-stack::BucketName
            S3Key: !stack_output my-other-stack::KeyName
            S3ObjectVersion: !s3_version
    ```

### Function Makefile

Each function has own `Makefile` file inside it's root.

Why `make`, you might ask. Because it's cross-platform tool, proven with years.

**Important!** Instructions and logic in `Makefile` are outside of `s3_package` responsibility.
Hook does not know what and how should be installed, except one rule:

> All files for packaging should be placed into `dist` directory, inside function root.

Sample `Makefile` for `Python 2.7` Lambda with dependencies installed with `pip`:

```make
SHELL := bash
TARGET := dist

# Runtime: Python 2.7
PIP := pip2
SOURCES := $(wildcard *.py)

.PHONY: all
all:
	@ rm -rf $(TARGET) && mkdir -p $(TARGET)

	@ printf '[install]\nprefix=\n' > setup.cfg # OSX hack
	$(PIP) install -U -t $(TARGET) -r requirements.txt | grep -i 'installed'

	/bin/cp -f $(SOURCES) $(TARGET)/

	@ rm -rf setup.cfg $(TARGET)/*.so $(TARGET)/*.dist-info $(TARGET)/*.eggs $(TARGET)/*.egg-info
	@ find $(TARGET) -type f -name "*.py[cod]" -delete

	# Files for distribution:
	@ cd $(TARGET); find . -type f | sort -V | sed -e 's,^\./,  ,'
```

Explanation:

- variable `TARGET := dist` is convention over configuration, which defines distribution directory.

  _It should not be changed, otherwise hook `s3_package` won't find files for packaging._

- re-/create `dist` directory, to avoid distribution pollution
- apply OS X hack to allow `pip` install packages into alternative directory
- install dependencies with `pip` into `dist` directory
- copy all `*.py` source files into `dist` directory
- remove unattended files from `dist` directory

Feel free to adjust `Makefile` as you like, e.g., use `Docker` to build, just pay attention to `/dist/` directory.

### S3 encryption

There is a trick if you are using **encryption** on S3.

According to https://docs.aws.amazon.com/AmazonS3/latest/API/RESTCommonResponseHeaders.html documentation,
ETag `may` or `may not` be an **MD5 digest** of the object data.

1. Objects encrypted by SSE-S3 or plaintext, have ETags that `are` an MD5 digest of their object data.
2. Objects encrypted by SSE-C or SSE-KMS, have ETags that `are not` an MD5 digest of their object data.
3. Object is created by either the Multipart Upload or Part Copy operation, the ETag `is not` an MD5 digest, regardless of the encryption method.

In use-case `1` hook won't upload archive twice, as content MD5 and ETag do match.

> using `SSEAlgorithm: AES256` on S3 bucket will enable default encryption

In other use-cases hook will upload archive every time it's called, as content MD5 and ETag do not match.

> it might be required to build custom MD5/ETag lookup solution and adjust hook.

#### Caveats

- note that Sceptre `v1.3.4` was tested only and it may misbehave on previous versions.
- when running `Sceptre` from OSX, some packages may contain binary inside, so be sure to upload the proper one.
- custom encryption might require custom MD5/ETag lookup solution, see [S3 encryption](#s3-encryption)

## How to Contribute

We encourage contribution to our projects, please see our [CONTRIBUTING](CONTRIBUTING.md) guide for details.

## License

**sceptre-zip-code-s3** is licensed under the [Apache Software License 2.0](LICENSE.md).

## Thanks

Keep It Cloudy ([@CloudreachKIC](https://twitter.com/cloudreachkic))
