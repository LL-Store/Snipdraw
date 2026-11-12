; Snipdraw 的 Windows 安装包脚本（Inno Setup 6）。
; 由 packaging/build.py 调用，版本与路径通过 /D 传入：
;   ISCC.exe /DAppVersion=0.1.0 /DSourceDir=<dist\Snipdraw> /DOutputDir=<release> installer.iss
;
; 安装策略：装到当前用户目录（%LOCALAPPDATA%\Programs\Snipdraw），不需要管理员；
; 卸载不删用户配置（配置在 QStandardPaths 的 AppConfigLocation 下）。

#define AppName "Snipdraw"
#define AppExeName "Snipdraw.exe"
#define AppPublisher "LL-Store"
#define AppUrl "https://github.com/LL-Store/Snipdraw"

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Snipdraw"
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif

[Setup]
; AppId 一旦发布就不能改，否则新版本会被当成另一个软件
AppId={{7A26B4C5-3E1F-4B8A-9D2C-5F6E7A8B9C01}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
; 当前用户安装：免 UAC，卸载项仍会出现在「应用和功能」里
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=Snipdraw-{#AppVersion}-windows-x64-setup
SetupIconFile=..\assets\Snipdraw.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
AllowNoIcons=yes
LicenseFile=..\LICENSE
; 覆盖安装时关掉正在跑的托盘实例，装完让用户自己选是否启动
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "立即运行 {#AppName}"; Flags: nowait postinstall skipifsilent
