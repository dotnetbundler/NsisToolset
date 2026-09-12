# NsisToolset

[English](README.md)

NsisToolset 将 NSIS 打包为带版本、可重定位的 Windows、Linux 和 macOS
构建工具集，无需在系统中安装 NSIS。

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

启动器会自动选择当前宿主的编译器并配置 `NSISDIR`。校验命令见
[消费者指南](docs/consumer-guide.md)。

## 文档

- [消费者指南](docs/consumer-guide.md)
- [构建与发布](docs/build-and-release.md)
- [登记上游版本](docs/upstream-registration.md)
- [来源与构建策略](docs/source-and-build.md)

运行测试：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s tests -v
```

仓库自动化采用 MIT 许可。每个工具集归档都在 `common/COPYING` 中包含
NSIS 许可证。
