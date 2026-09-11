# NsisToolset

NsisToolset 是一个独立、通用的完整 NSIS 跨宿主工具集生产与发行项目。任何构建工具、框架、CI 系统或个人都可以下载带版本的 Release，校验 Manifest，选择对应宿主运行集并使用，无需安装 NSIS。本仓库不包含任何下游产品或 Bundler 的业务逻辑。

当前工具集版本：**`3.12-r1`**（上游 `3.12`，我们的包装修订 `r1`）。

## 已修正的方案前提

`NSIS_CONFIG_CONST_DATA_PATH=no` 不能自动发现独立放置的顶层 `common/`。因此每个宿主记录都明确声明真实 `binary` 和必需的 `NSISDIR=common` 环境契约。

程序化消费者应把 `binary` 和 `requiredEnvironment` 相对于解压后的工具集根目录解析，然后直接启动二进制。命令行用户可在 Windows 运行根目录 `makensis.cmd`，在 Linux/macOS 运行根目录 `makensis`；后者根据 `uname` 选择宿主，未知系统或架构会明确失败。

官方 Windows ZIP 中有两个 `makensis.exe`：根目录约 2.5 KiB 的文件只是启动器；真正运行集是 `Bin/makensis.exe` 和它依赖的 `Bin/zlib1.dll`。Linux 编译器要求完全静态链接；macOS 仅允许 Apple 系统动态库。CI 会实际检查这些约束。

## 产物结构

```text
makensis
makensis.cmd
common/
  Include/ Plugins/ Stubs/ Contrib/
  nsisconf.nsh COPYING
hosts/
  win-x86/      makensis.exe zlib1.dll
  linux-x64/    makensis
  linux-arm64/  makensis
  osx-x64/      makensis
  osx-arm64/    makensis
build-record.json
SOURCE-RECORD.md
toolset-manifest.json
```

`common/` 来自完全匹配版本的官方标准 ZIP，不按宿主重复。`Plugins` 是生成 Windows 安装器时使用的目标数据，不是当前构建宿主的动态依赖。

Manifest 为每个文件记录路径、SHA-256、大小、标准 Unix mode 和是否必须可执行；为每个宿主记录 RID、架构、兼容宿主 RID、真实二进制、必需环境变量、运行集文件及最低系统说明。官方 Windows 编译器实际是 PE x86，因此命名为 `win-x86`；对 x64 Windows 的兼容性单独记录。ZIP 解压后应恢复 Manifest 声明的可执行权限。

## 构建与验收

CI 使用真正的 Ubuntu 24.04 x64/arm64、macOS 15 Intel/Apple Silicon 和 Windows Server 2022 runner。原生编译器从官方源码执行 `install-compiler`，跳过 stubs、plugins、utils、misc 和 docs；公共数据始终来自完全匹配的官方 Windows ZIP。

每个原生编译器在同一 runner 构建两次并要求字节相同，随后检查动态选择的上游版本，通过真实二进制和根目录启动器分别编译最小 fixture。组装阶段检查完整文件集合、哈希、版本、权限策略、宿主元数据，并在含空格的新路径解压和运行。最终 Windows job 会逐一实际运行五个宿主生成的安装器，检查安装标记，运行卸载器并确认清理完成。

## 仓库中的 Python 文件

- `scripts/toolset.py`：下载并校验上游输入、组装宿主、生成和验证 Manifest、创建确定性 ZIP。
- `scripts/host_metadata.py`：记录原生编译器、runner、工具链、依赖和构建参数。
- `scripts/provenance.py`：把各宿主记录与 GitHub Actions provenance 汇总。
- `scripts/register-upstream.cmd` 与 `scripts/register-upstream.sh`：无需语言运行时，在本地登记上游校验信息。
- `tests/test_toolset.py`：测试完整性失败、确定性打包、路径安全、权限元数据和宿主调用契约。

这些文件只用于下载、构建、组装、验证和测试，不会进入最终 NSIS toolset，也不是任何下游使用依赖。选择 Python 是因为同一套组装逻辑需要跨 Windows、Linux 和 macOS 运行，而且 NSIS 自身的 SCons 源码构建本来就需要 Python。

Linux 使用静态用户态二进制，并校验 GNU ABI note（x64 内核基线 3.2，arm64 为 3.7）。macOS deployment target 分别为 10.13（x64）和 11.0（arm64）。这些是构建基线；实际 CI 环境会写入 provenance。Windows Server 2022 已验证，但本项目不替上游宣称更老的 Windows 兼容性。

本地可完成、不需要全部原生系统的检查：

```powershell
python scripts/toolset.py --upstream-config config/upstream/3.12.json --toolset-version 3.12-r1 download --cache .cache/upstream
python scripts/toolset.py --upstream-config config/upstream/3.12.json --toolset-version 3.12-r1 stage-windows --archive .cache/upstream/nsis-3.12.zip --stage stage --work artifacts/work
python -m unittest discover -s tests -v
```

完整原生构建放在 CI 中，避免用 Windows 交叉环境冒充 macOS。完整参数、输入哈希和“无补丁”记录见 [SOURCES.md](SOURCES.md)。

## 发布与消费

只有推送 tag 或手动触发才启动工作流。版本格式为 `v<已登记上游版本>-<本地标识>`，例如 `v3.12-r1`、`v3.12-preview.2`。手动触发只构建和验证；合法 tag 推送在全部安装/卸载验收通过后发布。正式资产包括 ZIP、ZIP 的 SHA-256、`toolset-manifest.json` 和 `build-provenance.json`。

Actions 临时 artifact 只用于 job 间传递。消费者必须使用带版本的 GitHub Release 资产，固定外层 ZIP SHA-256，校验内部 Manifest，只选择一个宿主，恢复权限，设置声明的环境变量，并分发或调用 `common/` 与该宿主运行集。不得使用 Actions artifact 或 `latest` URL。`DotNet.Bundler.Nsis` 只是一个可能的消费者，不享有特殊地位，也不定义本项目规范。

## 升级流程

1. 选择明确的 NSIS 上游版本与新的包装修订号。
2. Windows 运行 `scripts/register-upstream.cmd`，Linux/macOS 运行 `scripts/register-upstream.sh`，人工检查生成的 `config/upstream/<版本>.json`；不同本地标识复用同一文件。
3. 重新审计官方 ZIP 结构，尤其是真实 Windows 编译器与全部运行时依赖。
4. 审查上游构建参数及 `Source/exehead/config.h` 的兼容约束；公共数据和原生编译器源码必须完全匹配。
5. 跑完整原生矩阵、重复构建比较、重定位测试和全宿主 Windows 安装/卸载测试。
6. 审查上游许可变化，更新中英文文档，创建精确版本 tag，由受保护 workflow 一次性发布。

## 来源与许可

SourceForge 为两个上游归档公布 SHA-1 和 MD5；本项目对从官方 URL 下载的实际字节独立计算 SHA-256，不把 SHA-256 说成上游公布值。下载只有在字节数、上游公布 SHA-1 和本地派生 SHA-256 同时匹配时才接受；MD5 仅作为来源一致性记录，不作为安全校验。准确数值见 [SOURCES.md](SOURCES.md)。解压会拒绝路径穿越，Actions 使用明确的完整发布版本，SCons wheel 固定版本与哈希。本仓库原创自动化采用 MIT 许可；每个工具集都在 `common/COPYING` 保留 NSIS 上游许可。

- Windows ZIP：上游公布 SHA-1 `364fd795b0cafc1fbff3e966f103a8f8fc8fb7f1`，上游公布 MD5 `757c22153dd8b90f5e297310d9966997`，本地派生 SHA-256 `56581f90db321581c5381193d796fffcf2d24b2f8fed2160a6c6a3baa67f2c4f`。
- 源码包：上游公布 SHA-1 `432e99150881c061c7e313eb1aac45763d951572`，上游公布 MD5 `8ec7c3e1228ac4eb96e5e421610b4aae`，本地派生 SHA-256 `f3ed7a8e4aa2cf4e8cf47d3b563a02559e0cb4934db2662b2f9661b824e2b186`。
