# agentcore-push ナレッジ

## ドキュメント作成ルール

`docs/` 配下の Markdown は、みのるんが読みやすいよう必ず日本語で書く。英語の技術用語や API 名はそのまま使ってよいが、説明文は日本語にする。

## Direct Code Deployment

Amazon Bedrock AgentCore Runtime は Direct Code Deployment に対応している。ZIP のデプロイパッケージを S3 へアップロードし、S3 上の保存先を `CreateAgentRuntime` または `UpdateAgentRuntime` に渡してデプロイする。

Python パッケージにネイティブバイナリが含まれる場合、依存関係には Linux ARM64 との互換性が必要になる。公式ガイドでは次のように `uv pip install` を使っている。

```bash
uv pip install \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.13 \
  --target=deployment_package \
  --only-binary=:all: \
  -r pyproject.toml
```

## AgentCore Runtime のエントリポイント

Python ファイルは、次のどちらかの形で書く必要がある。

- `BedrockAgentCoreApp` と `@app.entrypoint` を使う。
- `/invocations` の POST と `/ping` の GET エンドポイントを実装する。

Strands と AgentCore Observability を組み合わせる場合は、次の import を優先する。

```python
from bedrock_agentcore import BedrockAgentCoreApp
```

次の import は避ける。

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
```

トレースの初期化では、トップレベルから import することが重要になる。

## GitHub Codespaces 前提

ハンズオン参加者のローカル環境の違いに左右されない体験にしたいため、最初の MVP は GitHub Codespaces を対象にする。

MVP では Dev Container を使わず、標準の Codespace に `uv` をインストールして `aws login --remote` で認証する流れにする。

PyPI 公開後は、次の1コマンドで実行できる形を理想としている。

```bash
uvx agentcore-push agent.py
```

PyPI へ公開する前の開発中は、チェックアウトしたリポジトリから次のように実行する。

```bash
uvx --from . agentcore-push agent.py
```

## AWS Login

MVP では、AWS SDK のデフォルト認証チェーンが使える状態を前提にする。Codespaces では新しい AWS CLI のログイン機能を使う。

```bash
aws login --remote
```

新しい AWS CLI のローカル開発向けログインでは、`aws login` がデフォルトプロファイルを更新し、SDK からキャッシュ済みの一時認証情報を使えるようになる。

CLI パッケージには `botocore[crt]` を含めておく。そうしておくと、`aws login` のフローで SDK 側の認証情報更新が動きやすくなる。

従来の SSO プロファイル更新として `aws sso login` も使えるが、この OSS のハンズオンは `aws login --remote` を前提にする。

既存の SSO 設定済みプロファイルに対して `aws login --profile <existing>` を実行すると、`Profile '<name>' is already configured with SSO credentials` で失敗する。この場合は既存の設定を壊さずに、検証用のプロファイルを作る。

```bash
aws configure set region us-east-1 --profile agentcore-push-sandbox
aws login --remote --profile agentcore-push-sandbox
```

## 実行ロールの自動作成

`--role-arn` を指定しない場合は、SDK が作った既存ロールを推定して選ぶのではなく、`agentcore-push` 専用のロールを作成または再利用する。

```text
AmazonBedrockAgentCorePushRuntime-<region>
```

既存の `AmazonBedrockAgentCoreSDKRuntime-<region>-*` が複数あるアカウントでも、この専用ロールを使うので候補選択で止まらない。

公式ドキュメントの Runtime 実行ロールの要件に合わせ、信頼ポリシーでは `bedrock-agentcore.amazonaws.com` に `sts:AssumeRole` を許可し、`aws:SourceAccount` と `aws:SourceArn` で対象のアカウントとリージョンに絞る。

インラインポリシー `AgentCorePushRuntimeExecutionPolicy` には、CloudWatch Logs、X-Ray、CloudWatch Metrics、Bedrock モデル呼び出しの権限を含める。シンプルな Strands Agent の Direct Code Deployment を目的にしているため、Memory や Identity などの追加機能が必要な場合は `--role-arn` で専用ロールを渡せるようにしておく。

## 既知のリスク

- 呼び出し元に `iam:CreateRole`、`iam:PutRolePolicy`、`iam:PassRole` がない場合、実行ロールの自動作成または Runtime の作成が失敗する。
- ARM64 wheel がない依存関係は、パッケージング時または Runtime の検証時に失敗する。
- Direct Code Deployment はまだ新しいため、API の形が変わる可能性がある。AWS API の呼び出し部分は分離しておく。

## 実デプロイ検証メモ

2026-05-14 JST に sandbox アカウント `123456789012` / `us-east-1` で検証した。

- `uvx --no-cache --from . agentcore-push test.py --profile agentcore-push-sandbox --region us-east-1 --role-arn arn:aws:iam::123456789012:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-0d6e4079e3 --no-wait`
- Runtime ID: `test-YMjALfEemx`
- Runtime ARN: `arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test-YMjALfEemx`
- 作成後、`READY` に遷移した。
- `aws bedrock-agentcore invoke-agent-runtime` で `{"prompt":"こんにちは"}` を送信し、HTTP 200 と JSON の応答本文を確認した。
- 検証後、Runtime `test-YMjALfEemx`、S3 オブジェクト `test/deployment_package.zip`、検証で作成した S3 バケット `bedrock-agentcore-code-123456789012-us-east-1` は削除した。

quick start を実装したあとにも、同じ sandbox で回帰検証した。

- `uvx --no-cache --from . agentcore-push examples/test.py --profile agentcore-push-sandbox --region us-east-1 --role-arn arn:aws:iam::123456789012:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-0d6e4079e3`
- Runtime ID: `test-DFS4x24s1B`
- 作成から `READY` になるまでの待機を、CLI の wait 経路で確認した。
- `aws bedrock-agentcore invoke-agent-runtime` で `{"prompt":"こんにちは"}` を送信し、HTTP 200 と JSON の応答本文を確認した。
- 検証後、Runtime `test-DFS4x24s1B`、S3 オブジェクト、検証で作成した S3 バケットは削除した。

実行ロールの自動作成を実装したあとにも、同じ sandbox で回帰検証した。

- `uv run agentcore-push examples/test.py --profile agentcore-push-sandbox --region us-east-1`
- `--role-arn` なしで `AmazonBedrockAgentCorePushRuntime-us-east-1` が作成された。
- Runtime ID: `test-fcKWcaHgIH`
- 作成から `READY` になるまでの待機を、CLI の wait 経路で確認した。
- `aws bedrock-agentcore invoke-agent-runtime` で `{"prompt":"hello"}` を送信し、HTTP 200 と JSON の応答本文を確認した。
- 検証後、Runtime `test-fcKWcaHgIH` と S3 オブジェクト `test/deployment_package.zip` は削除した。
- `AmazonBedrockAgentCorePushRuntime-us-east-1` は次回再利用できるため、sandbox に残した。

## PyPI 公開

ローカルには PyPI API トークンを置かず、GitHub Actions の `publish.yml` から PyPI Trusted Publishing で公開する方針にする。

GitHub Release のリリースノートは、コミュニティの読みやすさを優先して英語で書く。`docs/` 配下の Markdown は日本語、公開向けの Release notes は英語と使い分ける。

PyPI 側では Trusted Publisher を次の内容で設定する。

- Owner: `minorun365`
- Repository: `agentcore-push`
- Workflow name: `publish.yml`

設定後、GitHub Release で `v0.1.0` を published にすると、`uv build` と `uv publish` が実行される。
