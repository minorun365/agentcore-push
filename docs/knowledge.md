# agentcore-push ナレッジ

## ドキュメント作成ルール

`docs/` 配下の Markdown は、みのるんが読みやすいように必ず日本語で書く。英語の技術用語や API 名はそのまま使ってよいが、説明文は日本語にする。

## Direct Code Deployment

Amazon Bedrock AgentCore Runtime は Direct Code Deployment に対応している。ZIP デプロイパッケージを S3 にアップロードし、その S3 の場所を `CreateAgentRuntime` または `UpdateAgentRuntime` に渡してデプロイする。

Python パッケージにネイティブバイナリが含まれる場合、依存関係は Linux ARM64 と互換である必要がある。公式ガイドでは次のように `uv pip install` を使う。

```bash
uv pip install \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.13 \
  --target=deployment_package \
  --only-binary=:all: \
  -r pyproject.toml
```

## AgentCore Runtime のエントリポイント

Python ファイルは次のどちらかを満たす必要がある。

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

トップレベル import を使うことが、トレース初期化で重要になる。

## GitHub Codespaces 前提

GitHub Codespaces を最初の MVP 対象にする。ハンズオン参加者のローカル環境差分に依存しない体験にしたいため。

MVP では Dev Container は不要。標準の Codespace から `uv` をインストールし、`aws login --remote` で認証する流れにする。

PyPI 公開後の理想形は次の1コマンド。

```bash
uvx agentcore-push agent.py
```

PyPI 未公開の開発中は、チェックアウト済みリポジトリから次のように実行する。

```bash
uvx --from . agentcore-push agent.py
```

## AWS Login

MVP では AWS SDK のデフォルト認証チェーンが使える状態を前提にする。Codespaces では新しい AWS CLI のログイン機能を使う。

```bash
aws login --remote
```

新しい AWS CLI のローカル開発向けログインでは、`aws login` がデフォルトプロファイルを更新し、SDK がキャッシュ済みの一時認証情報を使える。

CLI パッケージには `botocore[crt]` を含める。これにより、`aws login` フローで SDK 側の認証情報更新が動きやすくなる。

`aws sso login` は従来の SSO プロファイル更新として使えるが、この OSS のハンズオン前提は `aws login --remote` に寄せる。

既存プロファイルが SSO 設定済みの場合、`aws login --profile <existing>` は `Profile '<name>' is already configured with SSO credentials` で失敗する。この場合は、既存設定を壊さず検証専用プロファイルを作る。

```bash
aws configure set region us-east-1 --profile agentcore-push-sandbox
aws login --remote --profile agentcore-push-sandbox
```

## 実行ロールの自動作成

`--role-arn` 未指定時は、既存の SDK 生成ロールを推定して選ぶのではなく、`agentcore-push` 専用ロールを作成または再利用する。

```text
AmazonBedrockAgentCorePushRuntime-<region>
```

既存の `AmazonBedrockAgentCoreSDKRuntime-<region>-*` が複数あるアカウントでも、この専用ロールを使うため候補選択で停止しない。

公式ドキュメントの Runtime 実行ロール要件に合わせて、信頼ポリシーは `bedrock-agentcore.amazonaws.com` に `sts:AssumeRole` を許可し、`aws:SourceAccount` と `aws:SourceArn` で対象アカウントとリージョンに絞る。

インラインポリシー `AgentCorePushRuntimeExecutionPolicy` には、CloudWatch Logs、X-Ray、CloudWatch Metrics、Bedrock モデル呼び出しの権限を含める。シンプルな Strands Agent の Direct Code Deployment を目的にしているため、Memory や Identity などの追加機能が必要な場合は `--role-arn` で専用ロールを渡す余地を残す。

## 既知のリスク

- 呼び出し元に `iam:CreateRole`、`iam:PutRolePolicy`、`iam:PassRole` がない場合、実行ロールの自動作成または Runtime 作成が失敗する。
- ARM64 wheel がない依存関係は、パッケージング時または Runtime 検証時に失敗する。
- Direct Code Deployment はまだ新しいため、API 形状が変わる可能性がある。AWS API 呼び出し部分は分離しておく。

## 実デプロイ検証メモ

2026-05-14 JST に sandbox アカウント `715841358122` / `us-east-1` で検証した。

- `uvx --no-cache --from . agentcore-push test.py --profile agentcore-push-sandbox --region us-east-1 --role-arn arn:aws:iam::715841358122:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-0d6e4079e3 --no-wait`
- Runtime ID: `test-YMjALfEemx`
- Runtime ARN: `arn:aws:bedrock-agentcore:us-east-1:715841358122:runtime/test-YMjALfEemx`
- 作成後に `READY` へ遷移した。
- `aws bedrock-agentcore invoke-agent-runtime` で `{"prompt":"こんにちは"}` を送信し、HTTP 200 と JSON 応答本文を確認した。
- 検証後、Runtime `test-YMjALfEemx`、S3 オブジェクト `test/deployment_package.zip`、検証で作成した S3 バケット `bedrock-agentcore-code-715841358122-us-east-1` は削除済み。

quick start 実装後にも同じ sandbox で回帰検証した。

- `uvx --no-cache --from . agentcore-push examples/test.py --profile agentcore-push-sandbox --region us-east-1 --role-arn arn:aws:iam::715841358122:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-0d6e4079e3`
- Runtime ID: `test-DFS4x24s1B`
- 作成から `READY` 待ちまで CLI の wait 経路で確認した。
- `aws bedrock-agentcore invoke-agent-runtime` で `{"prompt":"こんにちは"}` を送信し、HTTP 200 と JSON 応答本文を確認した。
- 検証後、Runtime `test-DFS4x24s1B`、S3 オブジェクト、検証で作成した S3 バケットは削除済み。

実行ロール自動作成の実装後にも同じ sandbox で回帰検証した。

- `uv run agentcore-push examples/test.py --profile agentcore-push-sandbox --region us-east-1`
- `--role-arn` なしで `AmazonBedrockAgentCorePushRuntime-us-east-1` が作成された。
- Runtime ID: `test-fcKWcaHgIH`
- 作成から `READY` 待ちまで CLI の wait 経路で確認した。
- `aws bedrock-agentcore invoke-agent-runtime` で `{"prompt":"hello"}` を送信し、HTTP 200 と JSON 応答本文を確認した。
- 検証後、Runtime `test-fcKWcaHgIH` と S3 オブジェクト `test/deployment_package.zip` は削除済み。
- `AmazonBedrockAgentCorePushRuntime-us-east-1` は次回再利用できるため sandbox に残した。

## PyPI 公開

ローカルに PyPI API トークンを置かない方針にする。GitHub Actions の `publish.yml` から PyPI Trusted Publishing で公開する。

GitHub Release のリリースノートは、コミュニティの読みやすさを優先して英語で書く。`docs/` 配下の Markdown は日本語、公開向けの Release notes は英語、という分担にする。

PyPI 側では Trusted Publisher を次の内容で設定する。

- Owner: `minorun365`
- Repository: `agentcore-push`
- Workflow name: `publish.yml`

設定後、GitHub Release を `v0.1.0` で published にすると `uv build` と `uv publish` が実行される。
