# Neox NPK解包（Android 横屏全屏版源码）

## 本次调整
- 应用名称更改为「Neox NPK解包」。
- 固定横屏，并启用沉浸式全屏（隐藏状态栏与导航栏；系统手势/边缘操作可临时呼出系统栏）。
- 使用用户提供的猫咪参考图制作 Android 启动图标。
- 修复路径字典资产名：项目内文件是 `pathdict.txt.gz`，启动时按 gzip 原样复制到应用私有目录。
- 将用户提供的 `bnkextr` 与 `ww2ogg` 开源源码 ZIP 放入 assets，便于后续 Android NDK 移植。

## 当前功能边界
- NPK 资源解包、资源分类、常见图片和文本代码预览、单文件导出、全部资源 ZIP 导出由现有 Java/Python 代码实现。
- 目前不是完整的通用 3D 查看器；模型文件能显示信息并导出，但旋转/渲染需要额外集成适配的 3D 引擎和格式解析器。
- KTX/ASTC/DDS 等 GPU 贴图格式未保证全部可直接预览；原文件仍可导出。
- bnkextr/ww2ogg 目前作为开源源码随项目打包，尚未编译成 Android 可执行组件，也没有接入应用内一键音频转换。Windows 的 EXE 不能直接在 Android 上运行；需要使用 NDK 编译并实现 WEM→OGG 流程。转换为 MP3 还需另接编码器。
- 尚未在本环境执行成功的 Android Gradle 构建，因此请通过 GitHub Actions 构建后再安装测试。

## 音频工具原理（按用户提供说明）
BNK → bnkextr 提取 WEM → ww2ogg 转换 OGG → 可选再转换 MP3。项目中保留了两份源码 ZIP 供后续移植。
