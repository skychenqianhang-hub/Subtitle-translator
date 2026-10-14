; Inno Setup 脚本：把 dist\SubTranslator 打成安装包。
; 用法：先 build.bat 打包，再运行 installer\build_installer.bat（会把版本号从 app\version.py 读进来）。
; 产物：installer\output\SubTranslator-Setup-<版本>.exe

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "SubTranslator"
#define AppDisplayName "字幕翻译器 SubTranslator"
#define AppPublisher "Sky Chen"
#define AppURL "https://github.com/skychenqianhang-hub/Subtitle-translator"
#define AppExe "SubTranslator.exe"

[Setup]
AppId={{7D1C5C6E-3C0B-4C8B-9B6A-5F2C1D2E9A41}
AppName={#AppDisplayName}
AppVersion={#AppVersion}
AppVerName={#AppDisplayName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=output
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
ShowLanguageDialog=auto
; 安装过程中程序开着会失败：先提示关闭
CloseApplications=yes
RestartApplications=no

[Languages]
; 简体中文的语言文件 Inno Setup 官方包里没带（在官方仓库的 Unofficial 目录），放到 installer\ChineseSimplified.isl 后会自动用上
#if FileExists(AddBackslash(SourcePath) + "ChineseSimplified.isl")
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\SubTranslator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppDisplayName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppDisplayName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppDisplayName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#StringChange(AppDisplayName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 程序自己写的临时图标缓存；用户设置（API Key、场景）在 %APPDATA%\SubTranslator，卸载时保留
Type: filesandordirs; Name: "{localappdata}\Temp\SubTranslator"
