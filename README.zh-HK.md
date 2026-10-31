# 不用 S-DD1 的 Street Fighter Alpha 2

[English](README.md) | [日本語](README.ja.md) | [简体中文](README.zh-Hans.md) | 繁體中文 (香港)

[![ci](https://img.shields.io/github/actions/workflow/status/gufranco/snes-street-fighter-alpha-2-nochip/ci.yml?branch=main&style=flat-square&label=ci)](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/gufranco/snes-street-fighter-alpha-2-nochip?style=flat-square&label=release)](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/releases/latest)
[![license](https://img.shields.io/github/license/gufranco/snes-street-fighter-alpha-2-nochip?style=flat-square&label=license)](LICENSE)

Super Nintendo 版的 Street Fighter Alpha 2 與 Street Fighter Zero 2 把圖像壓縮存放，卡帶上的 S-DD1 晶片在遊戲運行時把它們解壓。沒有這塊晶片，遊戲甚麼也顯示不出來。

本項目建構一個不需要這塊晶片的映像檔。它預先解壓每一個圖像數據流，把結果排進一個 96 Mbit 的映像檔，並為遊戲加上修補，令它讀取這些數據。零售版卡帶的傾印需要你自備，這裏不含任何遊戲數據。

建構出來的映像檔在每場對戰前載入得更快，解鎖了真·豪鬼，還附有十一項錯誤修正。

## 你需要甚麼

- git 和 Docker。其他所有工具都在本項目的 Docker 映像中運行。
- 你自己卡帶的傾印，4,194,304 位元組，不帶拷貝機標頭：

| 卡帶 | 在 `roms/` 中的檔案名稱 | SHA-256 |
|:--|:--|:--|
| Street Fighter Alpha 2，美國版 | `sfa2-usa-final.sfc` | `910a29f834199c63c22beddc749baba746da9922196a553255deade59f4fc127` |
| Street Fighter Zero 2，日本版 | `sfz2-jp-final.sfc` | `f15731675e22dbf3882b777b2d8cd541a637dfdf5d8880c83903cf1e0b64590e` |

## 建構

1. 安裝 git 和 Docker。在 macOS 上，用 Docker Desktop 可以，執行 `brew install colima docker` 之後再執行 `colima start` 也可以。在 Windows 上，凡是本頁寫 `./run.sh` 的地方，請輸入 `.\run.cmd`。

2. 連同子模組一起複製儲存庫。從 GitHub 下載 ZIP 是行不通的，因為它不含九個固定的子模組。

   ```bash
   git clone --recurse-submodules https://github.com/gufranco/snes-street-fighter-alpha-2-nochip.git
   cd snes-street-fighter-alpha-2-nochip
   ```

3. 把傾印按上表中的名稱複製到 `roms/`，然後檢查它。第一次執行會建構 Docker 映像，需時數分鐘。

   ```bash
   ./run.sh tools/identify.py
   ```

4. 執行診斷工具。它會檢查複製、傾印和工具，並指出下一條要執行的指令。

   ```bash
   ./run.sh doctor.py
   ```

5. 建構。

   ```bash
   ./run.sh pack.py
   ```

[`pack.py`](pack.py) 會建構兩個地區，或只建構你指定的地區，例如 `./run.sh pack.py usa`。檔案輸出到 `dist/v<version>/`，每種裝置一個資料夾，並附有一個 `SHA256SUMS` 檔案。

## 用哪個檔案

每個資料夾裏都是同一個映像檔。不同的只有映像檔前面的 512 位元組和標頭宣告的晶片組，因為每種裝置都按它們決定如何映射映像檔。

| 資料夾 | 用於 | 檔案大小 |
|:--|:--|:--|
| `emulator` | snes9x 及其他模擬器 | 12,582,912 位元組 |
| `supereverdrive` | Super EverDrive | 12,582,912 位元組 |
| `sd2snes` | SD2SNES 及 SD2SNES Pro | 12,583,424 位元組 |
| `fxpak` | FXPAK Pro | 12,583,424 位元組 |
| `gamedoctor` | Game Doctor SF7 | 12,583,424 位元組 |

sd2snes 韌體只會在標頭宣告晶片 `$43` 或 `$45`、而且檔案剛好是 12,583,424 位元組時才使用它的 96 Mbit 映射，所以 `sd2snes` 和 `fxpak` 的檔案即使映像檔中沒有晶片，也會宣告晶片 `$43`。`gamedoctor` 的檔案附有映射全部 24 個 4 Mbit 區塊的 512 位元組標頭。

## 遊戲有甚麼改變

**每場對戰前的停頓更短。** 停頓來自聲音驅動程式，它每次只向音效晶片傳送一個位元組的取樣。修補後的驅動程式每次交握傳送三個位元組，並略過已經載入的取樣清單。

| | 零售版 | 本建構 |
|:--|:--|:--|
| 戰前最長停頓，美國版 | 2.90 秒 | 0.80 秒 |
| 戰前最長停頓，日本版 | 2.60 秒 | 0.72 秒 |

**解鎖真·豪鬼。** 他自 1996 年起就在卡帶裏，藏在一個直到 2021 年才有人記錄下來的秘技後面。

對遊戲本身程式碼的**十一項修正**：

| 修正 | 地區 |
|:--|:--|
| 在體力條、選角、對戰及結果畫面還原 Sodom 的名字 | 美國版 |
| 豪鬼的勝利姿勢改為街機次序 | 兩者 |
| 要求第九個影子幀時，存活物件數不再超出物件表 | 兩者 |
| 修正 Sagat 抓住 Dan 父親那一幀中的三條精靈記錄 | 兩者 |
| 把 45 處對空例程的呼叫改寫為直接返回 | 兩者 |

無晶片映像檔亦直接存放了那個 24,704 位元組的表，遊戲原本在每場對戰前要花 27 幀來建構它。

## 已測試的硬件

| 裝置 | 映像檔 | 結果 |
|:--|:--|:--|
| Game Doctor SF7，128 Mbit DRAM | 美國版及日本版，`gamedoctor` 檔案 | 進入對戰 |
| SD2SNES 及 SD2SNES Pro，韌體 1.11.2 | 美國版及日本版，`sd2snes` 檔案 | 進入對戰 |
| SD2SNES Mk.II 複製版，韌體 1.11.2 | 美國版，`sd2snes` 檔案 | 整個遊戲 |
| FXPAK Pro | 美國版，無晶片映像檔 | 運行 |
| Super EverDrive | 美國版，無晶片映像檔 | 標題畫面，出自 @yoshinokentarou 的[相片](https://x.com/yoshinokentarou/status/2111959864163664247/photo/1) |

SD2SNES、SD2SNES Pro 和 Game Doctor 的運行由 herrkuhn 完成，報告於 [issue 31](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/issues/31) 和 [issue 37](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/issues/37)。Mk.II 複製版的運行和下面的相片由 Hamilton Pimentel 提供，報告於 issue 31。

<p align="center">
  <img src="photos/sd2snes-mk2/01-sd2snes-in-a-super-famicom.jpg" width="250" alt="插在 Super Famicom 上並已開機的 SD2SNES 卡帶">
  <img src="photos/sd2snes-mk2/02-title-animation.jpg" width="250" alt="CRT 電視上的 Street Fighter Alpha 2 標題動畫">
  <img src="photos/sd2snes-mk2/03-title-screen.jpg" width="250" alt="附有 Capcom U.S.A. 版權行的標題畫面">
  <img src="photos/sd2snes-mk2/04-player-select.jpg" width="250" alt="選中隆的玩家選擇畫面">
  <img src="photos/sd2snes-mk2/05-ryu-against-ken.jpg" width="250" alt="對戰開始時面對面的隆和肯">
  <img src="photos/sd2snes-mk2/06-akuma-next-opponent.jpg" width="250" alt="標示下一個對手豪鬼和凱的街機地圖">
  <img src="photos/sd2snes-mk2/07-akuma-wins.jpg" width="250" alt="附有對白 Now stay down 的豪鬼勝利畫面">
  <img src="photos/sd2snes-mk2/08-ending-credits.jpg" width="250" alt="物件設計和聲音監修的片尾字幕">
  <img src="photos/sd2snes-mk2/09-thank-you-for-playing.jpg" width="250" alt="Capcom 出品的 thank you for playing 結束畫面">
</p>

在模擬器上，自從 [pull request 1082](https://github.com/snes9xgit/snes9x/pull/1082) 加入了這個映像檔所用的映射，snes9x 就能載入它。ares、Mesen2、bsnes 和 Mednafen 尚未試過。

## 已知限制

- 日本版數據流表是透過遊玩零售卡帶、記錄它向晶片要求了甚麼而找出來的，所以無法證明它是完整的。沒有人到過的畫面仍可能顯示錯誤。美國版的表是從帶標籤的傾印中讀出來的，沒有這種缺口。
- 有兩項修正，即物件表溢出和 Dan 父親的精靈，是根據閱讀程式碼得出的。沒有任何記錄過的運行到達過這兩個場景。
- FXPAK Pro 上運行普通 `.sfc` 的結果無法用韌體原始碼解釋。在這塊卡帶上請使用 `fxpak` 資料夾裏的檔案。

[OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) 列出了每一項限制，以及能確定它的量度。

## 報告問題

請附上 `./run.sh doctor.py` 的輸出，開一個 [issue](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/issues)。如果畫面不對，請說明你用的是哪個檔案和地區，並附上該畫面的相片或截圖。切勿附上 ROM 或從 ROM 解出的任何內容。

## 如何建構和檢查

每個數據流都用晶片的 Python 模型解壓，並與 snes9x 的 `sdd1emu.cpp` 逐位元組比較：美國版 2,817 個、日本版 2,855 個數據流，沒有任何不同。每個完成的映像檔都在模擬器測試工具上運行 12,000 幀，每次取樣上傳都與其來源比較。建構步驟、映像檔佈局、每條指令和 Python 介面都在 [REFERENCE.md](REFERENCE.md) 中。測試關卡見 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 鳴謝與參考

- Andreas Naive 逆向分析了 S-DD1 的壓縮演算法。
- DarkAkuma 的 SNES Classic 修補為美國版 ROM 中的每個數據流加上標籤，美國版數據流表由此而來。
- neviksti 的無晶片 Star Ocean 轉換是解壓器和記憶體映射的參照。
- 這裏使用的兩個反組譯器都以 bsnes 的反組譯表為基礎。
- Modern Vintage Gamer，[A closer look at Street Fighter Alpha 2 on the Super Nintendo](https://www.youtube.com/watch?v=fB9GlZUYNUQ)，講停頓從何而來。
- [Zeldix 上的 Street Fighter Alpha 2 討論串](https://www.zeldix.net/t1831-street-fighter-alpha-2)，有 gizaha 的修補和更新記錄。
- Nintendo Life，[After 25 Years, A New Cheat Code Has Been Discovered For Street Fighter Alpha 2 On The SNES](https://www.nintendolife.com/news/2021/01/after_25_years_a_new_cheat_code_has_been_discovered_for_street_fighter_alpha_2_on_the_snes)。
- Retroware，[The Curious Case of Street Fighter Alpha 2 on the SNES](https://articles.retroware.com/2021/03/08/the-curious-case-of-street-fighter-alpha-2-on-the-snes/)。
- [snes9x](https://github.com/snes9xgit/snes9x) 1.63，[issue 1081](https://github.com/snes9xgit/snes9x/issues/1081) 和 [pull request 1082](https://github.com/snes9xgit/snes9x/pull/1082)。

關於本項目的文章：吉野@連邦（[@yoshinokentarou](https://x.com/yoshinokentarou/status/2111959864163664247)）在 X 上的帖子，2026-10-18；Junior Candido 在 [Arkade](https://arkade.com.br/street-fighter-alpha-2-ganha-versao-para-super-nintendo-sem-o-chip-s-dd1-e-com-pausa-pre-luta-bem-menor/) 的文章，2026-10-20；Sonymaster 在 [Adrenaline 論壇](https://forum.adrenaline.com.br/threads/street-fighter-alpha-2-de-super-nintendo-ganha-versao-sem-o-chip-s-dd1-e-com-pausa-pre-luta-bem-menor.721807/)的轉載，2026-10-21。

引用本項目請使用 [CITATION.cff](CITATION.cff)。

## 授權

MIT，見 [LICENSE](LICENSE)。它涵蓋工具、組合語言程式碼和文件，不授予任何關於遊戲的權利。
