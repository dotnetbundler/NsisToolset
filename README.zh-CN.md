# NsisToolset

[English](README.md)

NsisToolset 将 NSIS 打包为带版本、可重定位的 Windows、Linux 和 macOS
构建工具集，无需在系统中安装 NSIS。

示例版本：**`3.12-r1`**（NSIS `3.12`，修订版本 `r1`）。

## 使用

从对应的 GitHub Release 下载带版本的 ZIP 和 `.sha256` 文件。校验哈希、
解压，然后运行根启动器：

```powershell
.\makensis.cmd path\to\installer.nsi
```

```sh
# 仅当解压工具未保留执行权限时运行。
chmod +x makensis hosts/*/makensis
./makensis path/to/installer.nsi
```

支持的 RID 为 `win-x86`、`linux-x64`、`linux-arm64`、`osx-x64` 和
`osx-arm64`。Windows x86 编译器也可通过 Windows 兼容能力在 x64 和 ARM64
上运行，但它不是 ARM64 原生程序。

程序化消费者应从 `toolset-manifest.json` 选择兼容宿主，恢复声明的执行权限，
相对于解压根目录解析二进制和必需环境变量，然后调用该二进制。详见
[消费者指南](docs/consumer-guide.md)。

## 文档

- [消费者指南](docs/consumer-guide.md)
- [构建与发布](docs/build-and-release.md)
- [登记上游版本](docs/upstream-registration.md)
- [来源与构建记录](docs/source-and-build.md)

运行测试：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s tests -v
```

仓库自动化采用 MIT 许可。每个工具集归档都在 `common/COPYING` 中包含
NSIS 许可证。
