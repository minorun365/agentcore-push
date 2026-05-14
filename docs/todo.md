# agentcore-push TODO

## MVP

- [x] プロダクト名を `agentcore-push` に決める。
- [x] 引数1つでデプロイする流れを定義する。
- [x] 最小対象環境を GitHub Codespaces にする。
- [x] Python パッケージを作成する。
- [x] Runtime 名の正規化を実装する。
- [x] ZIP パッケージ作成を実装する。
- [x] S3 アップロードを実装する。
- [x] AgentCore Runtime の create/update を実装する。
- [x] README に使い方を書く。
- [x] 純粋ロジックのローカルテストを追加する。
- [x] `uvx agentcore-push` で実行する導線にする。
- [x] 引数なし quick start を実装する。
- [x] `aws login --remote` で作成した検証プロファイルを使い、sandbox 環境へ実デプロイする。
- [x] デプロイした Runtime を invoke して HTTP 200 と応答本文を確認する。
- [x] GitHub Actions の CI workflow を追加する。
- [x] PyPI Trusted Publishing 用 workflow を追加する。

## 今後の候補

- [ ] `doctor` コマンドを追加する。
- [ ] `invoke` コマンドを追加する。
- [ ] `cleanup` コマンドを追加する。
- [ ] 実行ロール作成オプションを追加する。
- [ ] CodeBuild を使ったリモートパッケージングを追加する。
- [ ] PyPI の Trusted Publisher を設定する。
- [ ] `v0.1.0` の GitHub Release を作成して PyPI に公開する。
