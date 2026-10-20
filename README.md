# Server TestFlight Skill

个人维护的开源 Codex Skill：从 Linux 服务器协调云端 iOS 编译、服务器签名、API 上传和 TestFlight 测试发布。无需自己的 Mac；编译使用云端 macOS/Xcode。

这是一个可恢复的协调器及发布操作规范。签名、上传和审核适配器由各项目在服务器配置，接口说明见 [server-contract.md](skills/server-testflight/references/server-contract.md)。不包含任何个人项目源码、Apple 证书、密钥、账号资料或服务器配置，也不代表 Apple / GitHub 官方产品。

将 `skills/server-testflight` 复制到 Codex 的 skills 目录，调用 `$server-testflight`。入口：[SKILL.md](skills/server-testflight/SKILL.md)。

离线验证：`python3 -m unittest discover -s tests -v`。配置后先使用 `release.py --check`；它仅检查 GitHub 可访问性和配置形状，不会上传构建。发布授权仍由调用者决定。

MIT License。当前是个人项目，欢迎提 issue；不提供 SLA。
