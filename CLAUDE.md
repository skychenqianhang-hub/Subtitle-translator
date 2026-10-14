# 字幕翻译器：给 Claude Code 的开工须知

每次开始工作前先读这份文件，再读 `PLAN.md`（项目说明书，含每个阶段的进度记录和待定想法）。

## 用户与协作方式

- 用户不写代码。所有说明、提问、报告用中文，少用术语，必须用时顺带解释。
- 一次做一个阶段，做完停下，告诉用户：做了什么、怎么测试、需要确认什么。用户验收后才提交 git，提交后顺手 `git push`。
- 验收对象是打包后的独立程序 `dist\SubTranslator\SubTranslator.exe`，不是 `run.bat`。每次交付都要重新打包并跑自检。
- 用户不擅长取名，命名由我来定并说明理由。
- 界面上的说明和标注必须有依据、要精确。用户否决过「最新、最便宜」这种模糊说法，要求先查分语言的实测数据和价格再写。
- 遇到 PLAN.md 没写清楚的大方向，先问用户，不要自己拍板。

## 用户对界面的明确偏好

- 主窗口只有两个模式页：「实时翻译」和「视频翻译」。设置放右上角齿轮，里面只留 API Key、下载位置、场景管理。
- 常用选项（原文语言、翻译至、识别 / 翻译模型、场景、输出形式和内容）都放在主页上，不藏进设置。
- 输出内容用「原文 / 译文 / 原文 + 译文」的说法，不写死「中文」。用户计划以后做多语言互译。
- 字幕编辑器要像「编辑一页幻灯片」：在画面上直接拖字幕、调字体大小颜色位置，是生成视频前的样式设计工具；播放器保留，但只是输出效果预览。
- 输出文件（srt、带字幕的视频、文档、字幕工程 json）都放在视频旁边，用户确认过保持这样。

## 硬规则：游戏模式的反作弊风险

用户原话：「这个一定谨慎谨慎再谨慎。」账号被封是不可逆的损失，比功能缺失严重得多。

- 只用系统层面的公开接口：抓声音用 WASAPI loopback 或按进程抓音频；读聊天只读游戏自己写出的日志文件，或对屏幕区域截图做文字识别。
- 绝不向游戏进程注入代码、不读写游戏内存、不挂钩游戏的图形接口、不做叠加层注入。悬浮窗必须是独立的普通置顶窗口。
- 任何做法只要不能确定安全，先查该游戏反作弊的公开政策，把风险如实告诉用户，由用户决定。拿不准就不做。
- 动手做阶段 6 之前，先把方案和每一步的风险写给用户看。

## 这台电脑的环境

- 项目路径 `E:\自制ai\翻译软件`；Python 环境是 conda 的 `subtranslator`，解释器在 `C:\Users\Sky Chen\anaconda3\envs\subtranslator\python.exe`。
- `conda` 和 `pip` 的 exe 启动器是坏的（报 Unable to create process）。用 `C:\Users\Sky Chen\anaconda3\python.exe -m conda ...`，或环境内 `python.exe -m pip ...`。
- ffmpeg 装了两个 winget 包：完整版 `Gyan.FFmpeg`（开发时用）和精简版 `Gyan.FFmpeg.Essentials`（打包只带它）。工具进程的 PATH 里可能找不到 ffmpeg，统一用 `app/tools.py` 的 `find_ffmpeg()`。
- 打包：`python -m PyInstaller --noconfirm --clean SubTranslator.spec`。用户开着程序窗口时文件被占用，打包会失败，需要请用户先关掉窗口（不要替用户强行关）。
- 打包后自检：`SubTranslator.exe --check 结果文件路径`，退出码 0 且文件末行是「全部通过」。
- 自动测试都在 `tests/`，用 `python -m tests.test_xxx` 运行，全部不花钱（假的识别器和翻译器）。
- 批处理文件（.bat）含中文时必须存成 GBK 编码、CRLF 换行，否则 cmd 读出来是乱码。
- 用 Bash 写含反斜杠或中文引号的 Python 补丁容易被转义弄坏。改代码优先用编辑工具，或把补丁脚本写成文件再运行。

## API Key 与真实接口测试

- Key 只保存在 `%APPDATA%\SubTranslator\config.json`，绝不进代码、不进 git、不在对话里显示。
- 用户 2026-10-07 起有 OpenAI 和 Anthropic 两家的 Key。Claude 的联网生成词表、Claude 翻译线路（字幕翻译，日→简中、英→日）都已用真实接口跑通。
- 用用户的 Key 做真实测试前要先征得同意，并说明大概花多少钱。用户此前同意过用十几秒的测试音频做小额验证。

## 版本与发布

- GitHub CLI 装在 `C:\Program Files\GitHub CLI\gh.exe`（不在 PATH 里，用完整路径调用），已用用户账号登录。

- 版本号只改 `app/version.py`。发布 = 改版本 → 补 CHANGELOG.md → `python installer/build_installer.py`（PyInstaller + 自检 + Inno Setup）→ 打 tag → `gh release create` 上传 `installer/output/SubTranslator-Setup-<版本>.exe`。细节见 PLAN.md 7.7。
- README.md / README_en.md 面向外部用户，改了功能要同步；截图在 docs/screenshots。

## 远端仓库

`https://github.com/skychenqianhang-hub/Subtitle-translator`（2026-10-15 起**公开**，MIT 许可证；Releases 里有安装包，v1.0.0 已发布）。本地分支 `main` 跟踪 `origin/main`，凭据由系统凭据管理器保存。推送前确认没有密钥进仓库。

## 界面多语言（中 / 日 / 英）

- 新写的界面文字照常写中文，但必须包 `tr("中文", 参数…)`（`app/i18n.py`），不要用 f-string 拼界面文字。写完跑 `python tools_dev/i18n_wrap.py` 可自动包，再到 `app/locales/en.json`、`ja.json` 补译文，最后跑 `python -m tests.test_i18n`。
- 场景的内部名字、术语表、翻译风格、发给模型的提示词、输出文件名不翻。细节见 PLAN.md 第 7.45 节。

## 界面样式

- 全部样式在 `app/ui/theme.py`（一套 QSS + 三组配色），控件外观改那里。颜色角色用 objectName（`hint` / `statusOk` / `statusError` / `statusInfo` / `primary` / `modeButton` 等），状态文字用 `common.set_status(label, kind)`。**不要再在控件上手写 `setStyleSheet("color: …")`**，深色配色下看不见。细节见 PLAN.md 7.6。

## 术语表是多语言的

- 一行 = 一个词在各语言的写法 `{en: Jett, ja: ジェット, zh-Hans: 捷风}`（`app/core/profiles/glossary.py`）。交给翻译模型前用 `EffectiveProfile.glossary_for(原文语言, 目标语言)` 拼成 {原文词: 译文词}，不要直接用 `.glossary`。
- 预置 yaml 的术语是 `- {en: …, zh-Hans: …}` 一行一条；改预置词表后把 `preset_version` +1，用户没改过的才会自动升级。旧格式 `{原文: 中文}` 读入时自动转换。
- 自动测试默认是中文界面；测试里断言的中文文字不用改。

## 当前状态（2026-10-06）

阶段 0 到 5 全部完成并验收，另有：字幕设计器、文档输出、模型选型与标注、中英日词表、场景自动判断、程序瘦身（285MB）、界面多语言（中日英，2026-10-06 验收通过并提交）、翻译提示词的「观众表达习惯」跟随目标语言、译文风格四档（口语 / 字幕 / 半正式 / 正式）、多语言术语表、预置词表补齐繁体中文列（台港澳服官方译名 + 台湾玩家用语）（2026-10-07 验收通过并提交）、「让 AI 生成词表」（PLAN.md 7.49，固定用 Claude，含省钱改造，2026-10-07 验收通过并提交）、界面美化：主题样式表 + 三套可切换配色 + 两个主页按「输入 → 怎么翻 → 开始」重排、高级选项折叠、场景逐级下拉（PLAN.md 7.6，2026-10-09 验收通过并提交）。

待办，顺序未定：
0. 产品 logo：2026-10-09 出过五轮候选（tools_dev/logo_candidates*.py），用户都不满意，已搁置、说不用我来做；除非用户重新提起，不要主动做。
0. 界面美化后续：设置、场景管理、字幕编辑器、生成词表对话框按同样思路收拾（用户只会说好看不好看，每轮先给截图或样机 `tools_dev/mock_ui.py`）。
1. 词表校对（Valorant、CS2 的译名请用户过目；英 / 日已合并成一行，繁体列已填，低把握项列在 PLAN.md 7.48）。
2. 阶段 6 游戏模式（先看上面的硬规则）。
3. 延时 15 秒同步播放模式（PLAN.md 第 7.5 节，用户在重新考虑应用范围，不要主动开工）。
