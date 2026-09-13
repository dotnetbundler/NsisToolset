# NsisToolset

[English](README.md)

NsisToolset 将 NSIS 打包为便携式 Windows、Linux 和 macOS 工具集。下载并解压后即可使用，无需安装 NSIS。

## 使用

从对应的 [GitHub Release](https://github.com/dotnetbundler/NsisToolset/releases) 下载 `nsis-toolset-<version>.zip`。

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

#### Linux 兼容性

Linux 主机需要 glibc 2.17 或更高版本，不支持 Alpine Linux 等使用 musl 的系统。

## 发布流程

1. 按照 [登记上游版本](docs/upstream-registration.md) 登记配置，如发布版本已有配置则无需重新登记。
2. （可选）运行本地测试：`python -m unittest discover -s tests -v`
3. 推送 `v<upstream-version>-<local-label>`（如 `v3.12-r1`）格式的标签，工作流会自动发布并测试 Release。

## 许可证

仓库自动化采用 [MIT 许可证](LICENSE)。[NSIS 许可证](https://nsis.sourceforge.io/Docs/AppendixI.html) 随包放在 `common/COPYING`。
