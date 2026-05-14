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

## 実行ロール推定

`--role-arn` 未指定時は、まず定番のロール名を探す。

1. `AmazonBedrockAgentCoreSDKRuntime-<region>`
2. `AmazonBedrockAgentCoreSDKRuntime-<region>-*`
3. `AgentCoreRuntimeExecutionRole`

SDK Runtime ロール候補が複数ある場合は安全のため自動選択しない。候補 ARN を表示し、ユーザーに `--role-arn` を指定してもらう。

## 既知のリスク

- 実行ロールが存在しない場合、create/update は失敗する。
- 実行ロールにアーティファクト用 S3 バケットへの `s3:GetObject` 権限がない場合、AgentCore Runtime 作成が失敗する可能性がある。
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
