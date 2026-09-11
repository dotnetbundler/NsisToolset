# NsisToolset

NsisToolset 是 `DotNet.Bundler.Nsis` 所消费的完整 NSIS 跨宿主工具集生产项目，不包含 Bundler 业务逻辑。Bundler 在自身发布生产阶段下载、校验并嵌入一个不可变版本的工具集；最终应用开发者无需安装 NSIS，打包应用时也不会联网下载工具。

当前工具集版本：**`3.12-r1`**（上游 `3.12`，我们的包装修订 `r1`）。

## 已修正的方案前提

`NSIS_CONFIG_CONST_DATA_PATH=no` 只会让原生编译器按可执行文件位置推导数据目录，并不能自动发现独立顶层的 `common/`。因此每个宿主都有一个很薄的入口脚本：先把 `NSISDIR` 指向 `common/`，再运行真实编译器。消费端必须使用 Manifest 的 `entryPoint`，不能自行猜测二进制路径。

官方 Windows ZIP 中有两个 `makensis.exe`：根目录约 2.5 KiB 的文件只是启动器；真正运行集是 `Bin/makensis.exe` 和它依赖的 `Bin/zlib1.dll`。Linux 编译器要求完全静态链接；macOS 仅允许 Apple 系统动态库。CI 会实际检查这些约束。

## 产物结构

```text
common/
  Include/ Plugins/ Stubs/ Contrib/
  nsisconf.nsh COPYING
hosts/
  win/          makensis.cmd makensis.exe zlib1.dll
  linux-x64/    makensis makensis.bin
  linux-arm64/  makensis makensis.bin
  osx-x64/      makensis makensis.bin
  osx-arm64/    makensis makensis.bin
build/hosts/     各宿主构建元数据
build-provenance.json
SOURCE-RECORD.md
toolset-manifest.json
```

`common/` 来自完全匹配版本的官方标准 ZIP，不按宿主重复。`Plugins` 是生成 Windows 安装器时使用的目标数据，不是当前构建宿主的动态依赖。

Manifest 为每个文件记录路径、SHA-256、大小、标准 Unix mode 和是否必须可执行；为每个宿主记录 RID、入口、真实二进制、运行集文件及最低系统说明。ZIP 解压工具不一定恢复 executable bit，所以 Unix 消费端必须先校验所有文件，再对 `requiresExecutable=true` 的记录按 `unixMode` 执行 `chmod`。

## 构建与验收

CI 使用真正的 Ubuntu 24.04 x64/arm64、macOS 15 Intel/Apple Silicon 和 Windows Server 2022 runner。原生编译器从官方源码执行 `install-compiler`，跳过 stubs、plugins、utils、misc 和 docs；公共数据始终来自完全匹配的官方 Windows ZIP。

每个原生编译器在同一 runner 构建两次并要求字节相同，随后检查版本为 `v3.12`，通过可重定位入口编译最小 fixture。组装阶段检查完整文件集合、哈希、版本、权限策略、宿主元数据，并在含空格的新路径解压和运行。最终 Windows job 会逐一实际运行五个宿主生成的安装器，检查安装标记，运行卸载器并确认清理完成。

Linux 使用静态用户态二进制，并校验 GNU ABI note（x64 内核基线 3.2，arm64 为 3.7）。macOS deployment target 分别为 10.13（x64）和 11.0（arm64）。这些是构建基线；实际 CI 环境会写入 provenance。Windows Server 2022 已验证，但本项目不替上游宣称更老的 Windows 兼容性。

本地可完成、不需要全部原生系统的检查：

```powershell
python scripts/toolset.py download --cache .cache/upstream
python scripts/toolset.py stage-windows --archive .cache/upstream/nsis-3.12.zip --stage stage --work artifacts/work
python -m unittest discover -s tests -v
```

完整原生构建放在 CI 中，避免用 Windows 交叉环境冒充 macOS。完整参数、输入哈希和“无补丁”记录见 [SOURCES.md](SOURCES.md)。

## 发布与 Bundler 消费

普通 push 和 PR 只构建、验证，不发布。只有名称严格等于 `v3.12-r1` 的 tag 才会在全部安装/卸载验收通过后发布，而且发布命令不会覆盖已有版本。正式资产包括 ZIP、ZIP 的 SHA-256、`toolset-manifest.json` 和 `build-provenance.json`。

Actions 临时 artifact 只用于 job 间传递。`DotNet.Bundler.Nsis` 必须使用带版本的 GitHub Release 资产，固定外层 ZIP SHA-256，校验内部 Manifest，只选择一个宿主，恢复权限，并嵌入 `common/` 与该宿主运行集。不得使用 Actions artifact 或 `latest` URL。

## 升级流程

1. 选择明确的 NSIS 上游版本与新的包装修订号。
2. 在配置、workflow 和来源记录中同步更新版本 URL、字节数、SHA-256 与 `SOURCE_DATE_EPOCH`。
3. 重新审计官方 ZIP 结构，尤其是真实 Windows 编译器与全部运行时依赖。
4. 审查上游构建参数及 `Source/exehead/config.h` 的兼容约束；公共数据和原生编译器源码必须完全匹配。
5. 跑完整原生矩阵、重复构建比较、重定位测试和全宿主 Windows 安装/卸载测试。
6. 审查上游许可变化，更新中英文文档，创建精确版本 tag，由受保护 workflow 一次性发布。

## 来源与许可

下载内容只有在字节数和 SHA-256 同时匹配时才会接受，解压会拒绝路径穿越。Actions 固定到 commit，SCons wheel 固定版本与哈希。详细来源与参数见 [SOURCES.md](SOURCES.md)。本仓库原创自动化采用 MIT 许可；每个工具集都在 `common/COPYING` 保留 NSIS 上游许可。
