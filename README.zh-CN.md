# NsisToolset

[English](README.md)

NsisToolset 为 Windows、Linux 和 macOS 构建宿主生成带版本、可重定位的
NSIS 工具集。工具集包含共享的 NSIS 安装器数据、各受支持宿主的编译器运行集、
根启动器，以及机器可读的完整性和宿主元数据。消费者不需要在系统中安装 NSIS。

当前工具集版本：**`3.12-r1`**（上游 NSIS `3.12`，本地标签 `r1`）。

## 支持的宿主

| 工具集 RID | 构建宿主 | 编译器 |
| --- | --- | --- |
| `win-x86` | Windows x86、x64，或通过 x86 兼容能力运行的 ARM64 | 上游官方 PE x86 编译器 |
| `linux-x64` | Linux x64 | 原生静态编译器 |
| `linux-arm64` | Linux ARM64 | 原生静态编译器 |
| `osx-x64` | macOS Intel | 原生编译器 |
| `osx-arm64` | macOS Apple Silicon | 原生编译器 |

Windows ARM64 支持依赖 Windows x86 仿真，并不是原生 ARM64 编译器。

## 快速开始

从对应的 GitHub Release 下载带版本的 ZIP 和 `.sha256` 文件。校验外层 ZIP
哈希、解压，然后运行根启动器：

```powershell
.\makensis.cmd path\to\installer.nsi
```

```sh
chmod +x makensis hosts/*/makensis
./makensis path/to/installer.nsi
```

根启动器会把 `NSISDIR` 设置为包内的 `common/` 目录。程序化集成应读取
`toolset-manifest.json`，选择兼容的宿主记录，相对于解压根目录解析 `binary`
和 `requiredEnvironment`，恢复声明的可执行权限，然后直接调用真实二进制。

Release 布局、完整性校验、宿主选择契约和各资产含义见
[消费者指南](docs/consumer-guide.md)。

## 构建与发布

只有推送版本 Tag 或手动触发 workflow 才会开始构建。版本格式为
`v<已登记上游版本>-<本地标签>`，例如 `v3.12-r1` 或
`v3.12-preview.2`。手动触发会完成全部构建与验证，但不会创建 GitHub
Release。

流水线只下载一次每个上游归档，构建四个原生宿主，在 Windows 测试五个宿主
生成的安装器，在 Linux 组装 Release，并在指定环节要求重复构建或重复打包的
字节完全一致。

- [构建与发布指南](docs/build-and-release.md)
- [上游版本登记](docs/upstream-registration.md)
- [来源与构建记录](docs/source-and-build.md)

本地运行仓库单元测试：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s tests -v
```

仓库原创自动化采用 MIT 许可。重新分发的 NSIS 内容会在每个工具集归档的
`common/COPYING` 中保留上游许可证。
