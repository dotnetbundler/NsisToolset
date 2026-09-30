# NsisToolset

[English](README.md)

NsisToolset 将 NSIS 打包为便携式 Windows、Linux 和 macOS 工具集。下载并解压后即可使用，无需安装 NSIS。

## 使用

从对应的 [GitHub Release](https://github.com/dotnetbundler/NsisToolset/releases) 下载 `nsis-toolset-<version>.zip`。

发布附件和 ZIP 内部目录见 [发布文件结构](docs/release-file-structure.md)。

### 校验（可选）

下载 `.sha256` 文件用于校验。

Windows：

```powershell
$version = '<version>'
$expected = (Get-Content "nsis-toolset-$version.zip.sha256").Split()[0]
$actual = (Get-FileHash "nsis-toolset-$version.zip" -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw 'checksum mismatch' }
```

Linux：

```sh
sha256sum --check nsis-toolset-<version>.zip.sha256
```

macOS：

```sh
shasum -a 256 --check nsis-toolset-<version>.zip.sha256
```

### 运行

Windows：

```powershell
.\makensis.cmd path\to\installer.nsi
```

Linux 或 macOS：

```sh
./makensis path/to/installer.nsi
```

启动器会自动选择当前宿主的编译器并配置 `NSISDIR`。

### 常见问题

#### Linux 或 macOS 提示权限不足

如果解压工具没有保留执行权限，运行：

```sh
chmod +x makensis hosts/*/makensis
```

## 系统支持

以下为运行工具集的宿主系统要求；生成的安装器用于 Windows。

| 系统    | 宿主架构                             | 版本要求                                                                    |
| ------- | ------------------------------------ | --------------------------------------------------------------------------- |
| Windows | x86、x64、ARM64                      | [Windows 2000+](https://sourceforge.net/p/nsis/mailman/message/30230037/)。 |
| Linux   | x64、ARM64                           | glibc 2.17 或更高版本。                                                     |
| macOS   | x64（Intel）、ARM64（Apple Silicon） | macOS 10.13+。                                                              |

Windows 最低版本按上游开发者说明的编译器兼容目标记录。Windows 的跨架构运行机制参见微软的 [WOW64 说明](https://learn.microsoft.com/en-us/windows/win32/winprog64/running-32-bit-applications)和 [ARM 仿真说明](https://learn.microsoft.com/en-us/windows/arm/apps-on-arm-x86-emulation)。

Linux 依赖 `zlib` 压缩库（`libz.so.1`）和 glibc 的字符编码转换组件，后者用于读取 CP936 等非 UTF-8 脚本和语言文件。常规系统通常已包含这些组件，精简系统可能需要通过发行版的软件包补齐。

## 发布流程

1. 按照 [登记上游版本](docs/upstream-registration.md) 登记配置，如发布版本已有配置则无需重新登记。
2. （可选）运行本地测试：`python -m unittest discover -s tests -v`
3. 推送 `v<upstream-version>-<local-label>`（如 `v3.12-r1`）格式的标签，工作流会自动发布并测试 Release。

## 许可证

仓库自动化采用 [MIT 许可证](LICENSE)。[NSIS 许可证](https://nsis.sourceforge.io/Docs/AppendixI.html) 随包放在 `common/COPYING`。
