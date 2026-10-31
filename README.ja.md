# S-DD1なしのStreet Fighter Alpha 2

[English](README.md) | 日本語 | [简体中文](README.zh-Hans.md) | [繁體中文 (香港)](README.zh-HK.md)

[![ci](https://img.shields.io/github/actions/workflow/status/gufranco/snes-street-fighter-alpha-2-nochip/ci.yml?branch=main&style=flat-square&label=ci)](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/gufranco/snes-street-fighter-alpha-2-nochip?style=flat-square&label=release)](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/releases/latest)
[![license](https://img.shields.io/github/license/gufranco/snes-street-fighter-alpha-2-nochip?style=flat-square&label=license)](LICENSE)

スーパーファミコン版のStreet Fighter Alpha 2とStreet Fighter Zero 2は、グラフィックを圧縮して持っており、カートリッジ上のS-DD1チップがゲームの動作中にそれを展開します。このチップがないと、ゲームは何も表示しません。

このプロジェクトは、チップを必要としないイメージを作ります。すべてのグラフィックストリームを前もって展開し、その結果を96 Mbitのイメージに配置して、ゲームがそれを読むようにパッチを当てます。市販カートリッジのダンプはご自身で用意してください。ここにはゲームのデータは含まれていません。

できあがるイメージは、試合前の読み込みも速くなり、真・豪鬼が解放され、11個のバグ修正も入っています。

## 必要なもの

- gitとDocker。ほかのツールはすべて、このプロジェクトのDockerイメージの中で動きます。
- ご自身のカートリッジのダンプ。4,194,304バイトで、コピー機ヘッダーのないもの:

| カートリッジ | `roms/`でのファイル名 | SHA-256 |
|:--|:--|:--|
| Street Fighter Alpha 2、北米版 | `sfa2-usa-final.sfc` | `910a29f834199c63c22beddc749baba746da9922196a553255deade59f4fc127` |
| Street Fighter Zero 2、日本版 | `sfz2-jp-final.sfc` | `f15731675e22dbf3882b777b2d8cd541a637dfdf5d8880c83903cf1e0b64590e` |

## ビルド

1. gitとDockerをインストールします。macOSでは、Docker Desktopでも、`brew install colima docker`のあとに`colima start`でも動きます。Windowsでは、このページで`./run.sh`と書かれているところを`.\run.cmd`と入力してください。

2. サブモジュールごとリポジトリをクローンします。GitHubからのZIPダウンロードは動きません。固定された9つのサブモジュールが含まれないためです。

   ```bash
   git clone --recurse-submodules https://github.com/gufranco/snes-street-fighter-alpha-2-nochip.git
   cd snes-street-fighter-alpha-2-nochip
   ```

3. ダンプを上の表の名前で`roms/`にコピーし、確認します。最初の実行ではDockerイメージをビルドするため、数分かかります。

   ```bash
   ./run.sh tools/identify.py
   ```

4. ドクターを実行します。チェックアウト、ダンプ、ツールを確認し、次に実行するコマンドを示します。

   ```bash
   ./run.sh doctor.py
   ```

5. ビルドします。

   ```bash
   ./run.sh pack.py
   ```

[`pack.py`](pack.py)は両方のリージョンをビルドします。`./run.sh pack.py usa`のように名前を指定すれば、そのリージョンだけをビルドします。ファイルは`dist/v<version>/`に、機器ごとのフォルダーと`SHA256SUMS`ファイルとともに出力されます。

## どのファイルを使うか

どのフォルダーにも同じイメージが入っています。違うのは前に付く512バイトとヘッダーが宣言するチップセットだけで、各機器はそれを見てイメージの配置を決めます。

| フォルダー | 使う機器 | ファイルサイズ |
|:--|:--|:--|
| `emulator` | snes9xなどのエミュレーター | 12,582,912バイト |
| `supereverdrive` | Super EverDrive | 12,582,912バイト |
| `sd2snes` | SD2SNESとSD2SNES Pro | 12,583,424バイト |
| `fxpak` | FXPAK Pro | 12,583,424バイト |
| `gamedoctor` | Game Doctor SF7 | 12,583,424バイト |

sd2snesファームウェアが96 Mbitのマップを使うのは、ヘッダーがチップ`$43`または`$45`を宣言し、ファイルがちょうど12,583,424バイトのときだけです。そのため`sd2snes`と`fxpak`のファイルは、イメージにチップがなくてもチップ`$43`を宣言します。`gamedoctor`のファイルは、4 Mbitの24個の区画すべてを配置する512バイトのヘッダーを持っています。

## ゲームで変わること

**試合前の待ち時間が短くなります。** 待ち時間の原因はサウンドドライバーで、サンプルを1バイトずつオーディオチップに送っています。パッチ後のドライバーは1回のハンドシェイクで3バイトを送り、すでに読み込まれているサンプルリストは読み飛ばします。

| | 市販版 | このビルド |
|:--|:--|:--|
| 試合前の最長の待ち時間、北米版 | 2.90秒 | 0.80秒 |
| 試合前の最長の待ち時間、日本版 | 2.60秒 | 0.72秒 |

**真・豪鬼が解放されます。** 1996年からカートリッジに入っていましたが、2021年まで誰も記録していなかった隠しコマンドの裏にありました。

ゲーム自身のコードへの**11個の修正**:

| 修正 | リージョン |
|:--|:--|
| ライフバー、キャラクター選択、対戦、結果の各画面でソドムの名前を元に戻す | 北米版 |
| 豪鬼の勝利ポーズをアーケードの順序に | 両方 |
| 9つ目の影フレームが要求されたとき、生存オブジェクト数がオブジェクトテーブルを超えないように | 両方 |
| サガットがダンの父親をつかむ場面の3つのスプライトレコードを修正 | 両方 |
| 空のルーチンへの45個の呼び出しを、直接戻るように書き換え | 両方 |

チップなしイメージは、ゲームが毎試合の前に27フレームかけて作っていた24,704バイトのテーブルも、完成した形で持っています。

## 動作を確認したハードウェア

| 機器 | イメージ | 結果 |
|:--|:--|:--|
| Game Doctor SF7、128 Mbit DRAM | 北米版と日本版、`gamedoctor`のファイル | 試合まで到達 |
| SD2SNESとSD2SNES Pro、ファームウェア1.11.2 | 北米版と日本版、`sd2snes`のファイル | 試合まで到達 |
| SD2SNES Mk.IIのクローン、ファームウェア1.11.2 | 北米版、`sd2snes`のファイル | ゲーム全体 |
| FXPAK Pro | 北米版、チップなしイメージ | 動作 |
| Super EverDrive | 北米版、チップなしイメージ | タイトル画面。@yoshinokentarouさんの[写真](https://x.com/yoshinokentarou/status/2111959864163664247/photo/1)より |

SD2SNES、SD2SNES Pro、Game Doctorでの実行はherrkuhnさんによるもので、[issue 31](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/issues/31)と[issue 37](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/issues/37)で報告されました。Mk.IIのクローンでの実行と下の写真はHamilton Pimentelさんによるもので、issue 31で報告されました。

<p align="center">
  <img src="photos/sd2snes-mk2/01-sd2snes-in-a-super-famicom.jpg" width="250" alt="スーパーファミコンに挿して電源を入れたSD2SNESカートリッジ">
  <img src="photos/sd2snes-mk2/02-title-animation.jpg" width="250" alt="ブラウン管テレビに映るStreet Fighter Alpha 2のタイトルアニメーション">
  <img src="photos/sd2snes-mk2/03-title-screen.jpg" width="250" alt="Capcom U.S.A.の著作権表記があるタイトル画面">
  <img src="photos/sd2snes-mk2/04-player-select.jpg" width="250" alt="リュウを選んだプレイヤー選択画面">
  <img src="photos/sd2snes-mk2/05-ryu-against-ken.jpg" width="250" alt="試合開始時に向かい合うリュウとケン">
  <img src="photos/sd2snes-mk2/06-akuma-next-opponent.jpg" width="250" alt="次の対戦相手として豪鬼とガイが示されたアーケードの地図">
  <img src="photos/sd2snes-mk2/07-akuma-wins.jpg" width="250" alt="Now stay downという台詞のある豪鬼の勝利画面">
  <img src="photos/sd2snes-mk2/08-ending-credits.jpg" width="250" alt="オブジェクトデザインとサウンド監修のエンディングクレジット">
  <img src="photos/sd2snes-mk2/09-thank-you-for-playing.jpg" width="250" alt="Capcomによるthank you for playingの最後の画面">
</p>

エミュレーターでは、[プルリクエスト1082](https://github.com/snes9xgit/snes9x/pull/1082)でこのイメージが使うマップが追加されたため、snes9xで読み込めます。ares、Mesen2、bsnes、Mednafenは試していません。

## 問題の報告

`./run.sh doctor.py`の出力を添えて[issue](https://github.com/gufranco/snes-street-fighter-alpha-2-nochip/issues)を開いてください。画面がおかしい場合は、使ったファイルとリージョンを書き、その画面の写真かキャプチャーを添付してください。ROMやROMから展開したものは決して添付しないでください。

## ビルドと確認の方法

すべてのストリームはチップのPythonモデルで展開し、snes9xの`sdd1emu.cpp`とバイト単位で比較しています。北米版2,817本と日本版2,855本で、違いはありません。完成した各イメージはエミュレーターのハーネス上で12,000フレーム動かし、すべてのサンプル転送を元のデータと比較しています。ビルドの手順、イメージの配置、すべてのコマンド、Pythonのインターフェースは[REFERENCE.md](REFERENCE.md)にあります。テストのゲートは[CONTRIBUTING.md](CONTRIBUTING.md)にあります。

## クレジットと参考資料

- Andreas NaiveさんがS-DD1の圧縮アルゴリズムを解析しました。
- DarkAkumaさんのSNES Classic用パッチは北米版ROMのすべてのストリームにタグを付けており、それが北米版のストリームテーブルになりました。
- nevikstiさんのチップなしスターオーシャン変換が、展開処理とメモリマップの手本になりました。
- ここで使う2つの逆アセンブラーは、どちらもbsnesの逆アセンブラーの表に基づいています。
- Modern Vintage Gamer、[A closer look at Street Fighter Alpha 2 on the Super Nintendo](https://www.youtube.com/watch?v=fB9GlZUYNUQ)。待ち時間の原因について。
- [ZeldixのStreet Fighter Alpha 2のスレッド](https://www.zeldix.net/t1831-street-fighter-alpha-2)。gizahaさんのパッチと変更履歴。
- Nintendo Life、[After 25 Years, A New Cheat Code Has Been Discovered For Street Fighter Alpha 2 On The SNES](https://www.nintendolife.com/news/2021/01/after_25_years_a_new_cheat_code_has_been_discovered_for_street_fighter_alpha_2_on_the_snes)。
- Retroware、[The Curious Case of Street Fighter Alpha 2 on the SNES](https://articles.retroware.com/2021/03/08/the-curious-case-of-street-fighter-alpha-2-on-the-snes/)。
- [snes9x](https://github.com/snes9xgit/snes9x) 1.63、[issue 1081](https://github.com/snes9xgit/snes9x/issues/1081)と[プルリクエスト1082](https://github.com/snes9xgit/snes9x/pull/1082)。

このプロジェクトを引用するときは[CITATION.cff](CITATION.cff)を使ってください。

## ライセンス

MITです。[LICENSE](LICENSE)を参照してください。ツール、アセンブリ、ドキュメントが対象で、ゲームに関する権利は一切与えません。
