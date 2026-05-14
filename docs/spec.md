# agentcore-push 仕様

## CLI

```bash
uvx agentcore-push path/to/agent.py
```

このコマンドは `agent.py` を、ファイル名の stem から決めた AgentCore Runtime にデプロイする。たとえば `hello-agent.py` は、AgentCore Runtime 名で使える文字に合わせて `hello_agent` になる。

引数なしで実行した場合は、対話可能なターミナルなら quick start を起動する。

- カレントディレクトリ直下の `.py` ファイルを探す。
- `agent.py`、`main.py`、`app.py` を優先して並べる。
- 候補が1つなら確認してからデプロイする。
- 候補が複数なら番号で選ばせ、確認してからデプロイする。
- 候補がない場合、または非TTYの場合は使い方だけ表示して終了する。

開発中で PyPI 未公開の場合は、チェックアウトしたリポジトリから次のように実行する。

```bash
uvx --from . agentcore-push path/to/agent.py
```

## 対象環境の前提

MVP の基準環境は GitHub Codespaces とする。

- 標準の GitHub Codespaces 環境を使う。
- AWS CLI v2.32.0 以上を使う。
- `uv` / `uvx` がなければユーザーがインストールする。
- PyPI 公開後は `uvx agentcore-push ...` で実行する。
- 開発中は `uvx --from . agentcore-push ...` でローカルチェックアウトから実行する。
- `aws login --remote` で認証情報を用意する。
- リージョンはデフォルト AWS プロファイルに保存するか、`--region` で指定する。

## Runtime 名のルール

AgentCore Runtime 名は次のパターンに一致する必要がある。

```text
[a-zA-Z][a-zA-Z0-9_]{0,47}
```

`agentcore-push` はファイル名の stem を次のルールで正規化する。

- 使えない文字は `_` に置き換える。
- 連続した `_` は1つにまとめる。
- 先頭が英字でなければ `agent_` を付ける。
- 最大 48 文字に切り詰める。

## パッケージング

デプロイ用 ZIP には次を含める。

- 指定された Python ファイルを ZIP ルートに配置する。
- 標準依存関係を ZIP ルートにインストールする。
  - `bedrock-agentcore`
  - `strands-agents`

依存関係は Linux ARM64 向けに `uv pip install` でインストールする。

```bash
uv pip install \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.13 \
  --target <package-dir> \
  --only-binary=:all: \
  bedrock-agentcore strands-agents
```

AgentCore Direct Code Deployment の権限要件に合わせて、ZIP 内の POSIX パーミッションを設定する。

- ディレクトリ: `755`
- ファイル: `644`
- `__pycache__` と `*.pyc` は含めない。

## AWS リソース

デフォルトのアーティファクト用 S3 バケット名は次の形式にする。

```text
bedrock-agentcore-code-<account-id>-<region>
```

デフォルトのアーティファクトキーは次の形式にする。

```text
<runtime-name>/deployment_package.zip
```

バケットが存在しない場合、`agentcore-push` は対象リージョンにバケット作成を試みる。

## AgentCore API の動作

このツールは `bedrock-agentcore-control` API を使う。

新規作成時:

- `create_agent_runtime`
- `agentRuntimeName`: 正規化した Runtime 名
- `agentRuntimeArtifact.codeConfiguration.code.s3`: アップロード済み ZIP の場所
- `agentRuntimeArtifact.codeConfiguration.runtime`: `PYTHON_3_13`
- `agentRuntimeArtifact.codeConfiguration.entryPoint`: `[<file-name>.py]`
- `networkConfiguration`: `{"networkMode": "PUBLIC"}`
- `roleArn`: 明示指定されたロール、またはツールが推定したロール

更新時:

- `update_agent_runtime`
- `agentRuntimeName` が完全一致する既存 Runtime を探す。
- 既存 Runtime の `agentRuntimeId` を使う。
- コードアーティファクトを新しい ZIP に差し替える。

## 重要な制約

- ZIP パッケージの上限は圧縮後 250 MB。
- ZIP 展開後の上限は 750 MB。
- AgentCore Direct Code Deployment では ARM64 互換のネイティブ wheel が必要。
- エントリポイントファイルは ZIP ルートに存在し、`.py` で終わる必要がある。
- 実行ロールには AgentCore Runtime がログ出力、トレース出力、Bedrock モデル呼び出しを行うための権限が必要。

## 実行ロールの自動作成

`--role-arn` が指定されていない場合、`agentcore-push` は次のロールを作成または再利用する。

```text
AmazonBedrockAgentCorePushRuntime-<region>
```

このロールは `bedrock-agentcore.amazonaws.com` を信頼し、`aws:SourceAccount` と `aws:SourceArn` で対象アカウントと対象リージョンの AgentCore リソースに限定する。

インラインポリシー名は次の通り。

```text
AgentCorePushRuntimeExecutionPolicy
```

ポリシーには、Direct Code Deployment のシンプルな Strands Agent 実行に必要な次の権限を含める。

- CloudWatch Logs へのログ出力
- X-Ray へのトレース出力
- CloudWatch Metrics へのメトリクス出力
- Bedrock モデル呼び出し

既存の `AmazonBedrockAgentCoreSDKRuntime-<region>-*` ロール候補が複数あっても、自動選択はしない。代わりに `agentcore-push` 専用ロールを使う。

ユーザーが明示的に `--role-arn` を指定した場合は、そのロールをそのまま使う。
