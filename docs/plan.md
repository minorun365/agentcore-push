# agentcore-push 計画

## 目的

`agentcore-push <agent.py>` だけで、単一 Python ファイルの Strands Agent を Amazon Bedrock AgentCore Runtime へ Direct Code Deployment する。

## 最小対象環境

MVP では GitHub Codespaces を最初の対象環境にする。新しい Codespace から、できるだけ短い手順で使える状態を目指す。

1. Codespaces を開く。
2. `uv` がなければインストールする。
3. `aws login --remote` を実行する。
4. `aws sts get-caller-identity` で対象アカウントを確認する。
5. 未公開の開発中は `uvx --from . agentcore-push agent.py` を実行する。
6. PyPI 公開後は `uvx agentcore-push agent.py` を実行する。

## 位置づけ

- 公式 AgentCore CLI は多機能な本番向けツールとして扱う。
- `agentcore-push` は、ハンズオンや PoC で「1つの Python ファイルを最短で AgentCore Runtime に載せる」ための小さなツールにする。
- 最初の MVP では、プロジェクト雛形生成、CDK、コンテナビルド、管理コンソール側の細かい設定管理は扱わない。

## MVP の範囲

1. Python ファイル名から AgentCore Runtime 名を決める。
2. Python Direct Code Deployment 用の ZIP パッケージを作る。
3. Linux ARM64 向けの標準依存関係をインストールする。
   - `bedrock-agentcore`
   - `strands-agents`
4. 現在の AWS アカウントとリージョンにある S3 バケットへ ZIP をアップロードする。
5. 同名の AgentCore Runtime がなければ新規作成する。
6. 同名の AgentCore Runtime があれば更新する。
7. Runtime ARN、バージョン、ステータス、S3 アーティファクト URI、AWS アカウント、リージョンを表示する。
8. PyPI 公開後は `uvx agentcore-push agent.py` だけで実行できるようにする。

## MVP では扱わないこと

- IAM ロールの作成。
- ECR やコンテナデプロイ。
- CodeBuild によるリモートビルド。
- ローカル開発サーバー。
- invoke、ログ、トレース、cleanup、エンドポイント管理。
- エントリポイントの Python ファイルと依存 wheel 以外を含む複雑な複数ファイル構成。

## デフォルト前提

- ユーザーは GitHub Codespaces 上で実行している。
- Dev Container は不要。
- `aws login --remote` などで AWS SDK のデフォルト認証情報が使える状態になっている。
- デフォルトプロファイルに対象 AWS アカウントとリージョンが設定されている。
- 互換性のある AgentCore Runtime 実行ロールがすでに存在している。
- `--role-arn` が指定されていない場合は、よく使われる AgentCore Runtime 実行ロール名から推定する。
- ロール候補が複数あって安全に選べない場合は、ツールが候補を表示して `--role-arn` 指定を促す。

## 今後の候補

- `agentcore-push invoke <name> "prompt"`
- `agentcore-push doctor <agent.py>`
- `agentcore-push cleanup <name>`
- `--remote-build codebuild`
- ハンズオン用 AWS アカウント向けの IAM ロール作成オプション。
