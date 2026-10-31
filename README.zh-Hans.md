# 去除 S-DD1 的 Street Fighter Alpha 2

[English](README.md) | [日本語](README.ja.md) | 简体中文 | [繁體中文 (香港)](README.zh-HK.md)

[![ci](https://img.shields.io/github/actions/workflow/status/gufranco/snes-street-fighter-alpha-2-nochip/ci.yml?branch=main&style=flat-square&label=ci)](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/gufranco/snes-street-fighter-alpha-2-nochip?style=flat-square&label=release)](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/releases/latest)
[![license](https://img.shields.io/github/license/gufranco/snes-street-fighter-alpha-2-nochip?style=flat-square&label=license)](LICENSE)

Super Nintendo 版的 Street Fighter Alpha 2 和 Street Fighter Zero 2 把图形压缩存放，卡带上的 S-DD1 芯片在游戏运行时解压它们。没有这块芯片，游戏什么也显示不出来。

本项目构建一个不需要这块芯片的镜像。它预先解压每一个图形数据流，把结果排进一个 96 Mbit 的镜像，并给游戏打补丁让它读取这些数据。零售版卡带的转储需要你自己提供，这里不含任何游戏数据。

生成的镜像在每场对战前加载更快，解锁了真·豪鬼，还带有十一项错误修正。

## 你需要什么

- git 和 Docker。其他所有工具都在本项目的 Docker 镜像中运行。
- 你自己卡带的转储，4,194,304 字节，不带拷贝机头部：

| 卡带 | 在 `roms/` 中的文件名 | SHA-256 |
|:--|:--|:--|
| Street Fighter Alpha 2，美版 | `sfa2-usa-final.sfc` | `910a29f834199c63c22beddc749baba746da9922196a553255deade59f4fc127` |
| Street Fighter Zero 2，日版 | `sfz2-jp-final.sfc` | `f15731675e22dbf3882b777b2d8cd541a637dfdf5d8880c83903cf1e0b64590e` |

## 构建

1. 安装 git 和 Docker。在 macOS 上，Docker Desktop 可以，`brew install colima docker` 之后运行 `colima start` 也可以。在 Windows 上，凡是本页写 `./run.sh` 的地方，请输入 `.\run.cmd`。

2. 连同子模块一起克隆仓库。从 GitHub 下载 ZIP 不行，因为它不含九个固定的子模块。

   ```bash
   git clone --recurse-submodules https://github.com/gufranco/snes-street-fighter-alpha-2-nochip.git
   cd snes-street-fighter-alpha-2-nochip
   ```

3. 把转储按上表中的名字复制到 `roms/`，然后检查它。第一次运行会构建 Docker 镜像，需要几分钟。

   ```bash
   ./run.sh tools/identify.py
   ```

4. 运行诊断工具。它检查检出、转储和工具，并给出下一条要运行的命令。

   ```bash
   ./run.sh doctor.py
   ```

5. 构建。

   ```bash
   ./run.sh pack.py
   ```

[`pack.py`](pack.py) 构建两个地区，或者只构建你指定的地区，例如 `./run.sh pack.py usa`。文件输出到 `dist/v<version>/`，每种设备一个文件夹，并附带一个 `SHA256SUMS` 文件。

## 用哪个文件

每个文件夹里都是同一个镜像。不同的只有镜像前面的 512 字节和头部声明的芯片组，因为每种设备都根据它们决定如何映射镜像。

| 文件夹 | 用于 | 文件大小 |
|:--|:--|:--|
| `emulator` | snes9x 和其他模拟器 | 12,582,912 字节 |
| `supereverdrive` | Super EverDrive | 12,582,912 字节 |
| `sd2snes` | SD2SNES 和 SD2SNES Pro | 12,583,424 字节 |
| `fxpak` | FXPAK Pro | 12,583,424 字节 |
| `gamedoctor` | Game Doctor SF7 | 12,583,424 字节 |

sd2snes 固件只在头部声明芯片 `$43` 或 `$45`、并且文件恰好为 12,583,424 字节时才使用它的 96 Mbit 映射，所以 `sd2snes` 和 `fxpak` 的文件即使镜像中没有芯片也声明芯片 `$43`。`gamedoctor` 的文件带有映射全部 24 个 4 Mbit 块的 512 字节头部。

## 游戏里有什么变化

**每场对战前的停顿更短。** 停顿来自声音驱动，它每次只向音频芯片发送一个字节的采样。打过补丁的驱动每次握手发送三个字节，并跳过已经加载过的采样列表。

| | 零售版 | 本构建 |
|:--|:--|:--|
| 赛前最长停顿，美版 | 2.90 秒 | 0.80 秒 |
| 赛前最长停顿，日版 | 2.60 秒 | 0.72 秒 |

**解锁真·豪鬼。** 他从 1996 年起就在卡带里，藏在一个直到 2021 年才有人记录下来的秘技后面。

对游戏自身代码的**十一项修正**：

| 修正 | 地区 |
|:--|:--|
| 在体力条、选人、对战和结算画面恢复 Sodom 的名字 | 美版 |
| 豪鬼的胜利姿势改为街机顺序 | 两者 |
| 请求第九个影子帧时，存活对象数不再超出对象表 | 两者 |
| 修正 Sagat 抓住 Dan 父亲那一帧中的三条精灵记录 | 两者 |
| 把 45 处对空例程的调用改写为直接返回 | 两者 |

无芯片镜像还直接存放了那张 24,704 字节的表，游戏原本在每场对战前要花 27 帧来构建它。

## 已测试的硬件

| 设备 | 镜像 | 结果 |
|:--|:--|:--|
| Game Doctor SF7，128 Mbit DRAM | 美版和日版，`gamedoctor` 文件 | 进入对战 |
| SD2SNES 和 SD2SNES Pro，固件 1.11.2 | 美版和日版，`sd2snes` 文件 | 进入对战 |
| SD2SNES Mk.II 克隆版，固件 1.11.2 | 美版，`sd2snes` 文件 | 整个游戏 |
| FXPAK Pro | 美版，无芯片镜像 | 运行 |
| Super EverDrive | 美版，无芯片镜像 | 标题画面，出自 @yoshinokentarou 的[照片](https://x.com/yoshinokentarou/status/2111959864163664247/photo/1) |

SD2SNES、SD2SNES Pro 和 Game Doctor 的运行由 herrkuhn 完成，报告于 [issue 31](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/issues/31) 和 [issue 37](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/issues/37)。Mk.II 克隆版的运行和下面的照片由 Hamilton Pimentel 提供，报告于 issue 31。

<p align="center">
  <img src="photos/sd2snes-mk2/01-sd2snes-in-a-super-famicom.jpg" width="250" alt="插在 Super Famicom 上并已通电的 SD2SNES 卡带">
  <img src="photos/sd2snes-mk2/02-title-animation.jpg" width="250" alt="CRT 电视上的 Street Fighter Alpha 2 标题动画">
  <img src="photos/sd2snes-mk2/03-title-screen.jpg" width="250" alt="带有 Capcom U.S.A. 版权行的标题画面">
  <img src="photos/sd2snes-mk2/04-player-select.jpg" width="250" alt="选中隆的玩家选择画面">
  <img src="photos/sd2snes-mk2/05-ryu-against-ken.jpg" width="250" alt="对战开始时面对面的隆和肯">
  <img src="photos/sd2snes-mk2/06-akuma-next-opponent.jpg" width="250" alt="标出下一个对手豪鬼和凯的街机地图">
  <img src="photos/sd2snes-mk2/07-akuma-wins.jpg" width="250" alt="带有台词 Now stay down 的豪鬼胜利画面">
  <img src="photos/sd2snes-mk2/08-ending-credits.jpg" width="250" alt="对象设计和声音监修的片尾字幕">
  <img src="photos/sd2snes-mk2/09-thank-you-for-playing.jpg" width="250" alt="Capcom 出品的 thank you for playing 结束画面">
</p>

在模拟器上，自从 [pull request 1082](https://github.com/snes9xgit/snes9x/pull/1082) 加入了这个镜像所用的映射，snes9x 就能加载它。ares、Mesen2、bsnes 和 Mednafen 尚未试过。

## 报告问题

请附上 `./run.sh doctor.py` 的输出，开一个 [issue](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/issues)。如果画面不对，请说明你用的是哪个文件和地区，并附上该画面的照片或截图。绝不要附上 ROM 或从 ROM 中解出的任何内容。

## 如何构建和检查

每个数据流都用芯片的 Python 模型解压，并与 snes9x 的 `sdd1emu.cpp` 逐字节比较：美版 2,817 个、日版 2,855 个数据流，没有任何不同。每个完成的镜像都在模拟器测试工具上运行 12,000 帧，每次采样上传都与其来源比较。构建步骤、镜像布局、每条命令和 Python 接口都在 [REFERENCE.md](REFERENCE.md) 中。测试门禁见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 致谢与参考

- Andreas Naive 逆向分析了 S-DD1 的压缩算法。
- DarkAkuma 的 SNES Classic 补丁给美版 ROM 中的每个数据流都打了标签，美版数据流表由此而来。
- neviksti 的无芯片 Star Ocean 转换是解压器和内存映射的参照。
- 这里使用的两个反汇编器都基于 bsnes 的反汇编表。
- Modern Vintage Gamer，[A closer look at Street Fighter Alpha 2 on the Super Nintendo](https://www.youtube.com/watch?v=fB9GlZUYNUQ)，讲停顿从何而来。
- [Zeldix 上的 Street Fighter Alpha 2 讨论串](https://www.zeldix.net/t1831-street-fighter-alpha-2)，有 gizaha 的补丁和更新日志。
- Nintendo Life，[After 25 Years, A New Cheat Code Has Been Discovered For Street Fighter Alpha 2 On The SNES](https://www.nintendolife.com/news/2021/01/after_25_years_a_new_cheat_code_has_been_discovered_for_street_fighter_alpha_2_on_the_snes)。
- Retroware，[The Curious Case of Street Fighter Alpha 2 on the SNES](https://articles.retroware.com/2021/03/08/the-curious-case-of-street-fighter-alpha-2-on-the-snes/)。
- [snes9x](https://github.com/snes9xgit/snes9x) 1.63，[issue 1081](https://github.com/snes9xgit/snes9x/issues/1081) 和 [pull request 1082](https://github.com/snes9xgit/snes9x/pull/1082)。

引用本项目请使用 [CITATION.cff](CITATION.cff)。

## 许可证

MIT，见 [LICENSE](LICENSE)。它涵盖工具、汇编代码和文档，不授予任何关于游戏的权利。
