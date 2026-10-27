# NeoXLab Mobile（横屏资源浏览版）

这是一个 Android/Chaquopy 实验版 NPK 资源提取项目。默认横屏布局：顶部选择/解包/导出操作，左侧资源分类与文件列表，右侧预览区。

## 当前功能
- 从 Android 文件选择器选择 NPK 文件。
- 调用 `mobile_unpack.py` 提取当前解析器支持的 NXPK 资源，并按贴图、UI、3D模型、代码与配置、音频、其他分类。
- 右侧可直接预览 PNG/JPG/JPEG/WebP/BMP 图片。
- 可预览常见文本/代码文件（JSON、XML、Lua、JS、Python、CFG、YAML 等，最多显示 1 MB）。
- 对模型、KTX/ASTC/DDS 等资源显示格式、大小、路径和提示，并可导出原文件。
- 可单独导出选中的文件，或把全部解包结果导出为 ZIP。
- GitHub Actions 工作流可在线构建 Debug APK。

## 重要限制
- 当前版本**尚未集成通用 3D 渲染器**，因此模型文件目前显示资源信息，不会显示可旋转的 3D 模型画面。
- KTX、ASTC、DDS 等压缩贴图尚未接入右侧自动解码预览；可导出原文件。普通 PNG/JPG/WebP/BMP 可预览。
- NPK 的加密、索引模式和压缩方式因游戏版本而异；无法识别的包可能解包失败或保留为原始数据。
- 此源码包并非已验证安装的 APK。请将源码上传到 GitHub 并运行 Actions 构建，再安装生成的 Debug APK 测试。

## 在线构建
1. 将本项目源码上传到 GitHub 仓库。
2. 打开仓库的 **Actions**。
3. 选择 **Build NeoXLab Mobile Android APK**，点击 **Run workflow**。
4. 工作流成功后，进入运行记录底部的 Artifacts，下载 `NeoXLab-Mobile-debug-apk` 并解压取得 APK。
