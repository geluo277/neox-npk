package com.notx.unzip;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.view.Gravity;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.Bitmap;
import android.database.Cursor;
import android.provider.OpenableColumns;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.Charset;
import java.util.ArrayList;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import java.util.zip.GZIPOutputStream;

public class MainActivity extends Activity {
    private static final int PICK_NPK = 101, CREATE_ZIP = 102, CREATE_FILE = 103;
    private static final int BG = Color.rgb(20, 24, 32), PANEL = Color.rgb(29, 35, 46), PANEL2 = Color.rgb(37, 45, 58);
    private static final int TEXT = Color.rgb(231, 237, 245), MUTED = Color.rgb(154, 166, 184), ACCENT = Color.rgb(80, 160, 255);
    private Uri selectedUri;
    private File unpackDir, zipFile, pathDict, selectedExportFile;
    private TextView status, previewTitle, previewText, countText;
    private Button chooseButton, extractButton, saveButton, exportSelectedButton;
    private ProgressBar progress;
    private ImageView previewImage;
    private ListView fileList;
    private LinearLayout categoryBar;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final ArrayList<File> allFiles = new ArrayList<>(), shownFiles = new ArrayList<>();
    private final ArrayList<String> shownLabels = new ArrayList<>();
    private String activeCategory = "全部";
    private File currentFile;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        hideSystemBars();
        setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);
        if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
        pathDict = new File(getFilesDir(), "pathdict.txt.gz");
        try { ensurePathDict(); } catch (Exception ignored) { }
        buildInterface();
    }


    private void hideSystemBars() {
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            android.view.WindowInsetsController controller = getWindow().getInsetsController();
            if (controller != null) {
                controller.hide(android.view.WindowInsets.Type.statusBars() | android.view.WindowInsets.Type.navigationBars());
                controller.setSystemBarsBehavior(android.view.WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
        }
    }

    @Override public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) hideSystemBars();
    }

    private void buildInterface() {
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(dp(10), dp(8), dp(10), dp(8)); root.setBackgroundColor(BG);
        LinearLayout toolbar = new LinearLayout(this); toolbar.setGravity(Gravity.CENTER_VERTICAL); toolbar.setOrientation(LinearLayout.HORIZONTAL);
        TextView title = text("Neox NPK解包", 21, TEXT, true); toolbar.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
        chooseButton = button("选择 NPK"); toolbar.addView(chooseButton, wrap());
        extractButton = button("开始解包"); toolbar.addView(extractButton, wrap());
        saveButton = button("导出全部 ZIP"); saveButton.setEnabled(false); toolbar.addView(saveButton, wrap());
        root.addView(toolbar, new LinearLayout.LayoutParams(-1, -2));
        // Long logs (many unsupported texture formats) stay in a fixed-height scrollable area
        // so the category filters and resource list remain visible and tappable.
        ScrollView statusScroll = new ScrollView(this);
        statusScroll.setFillViewport(false);
        statusScroll.setVerticalScrollBarEnabled(true);
        status = text("请选择 NPK 文件。解包后可在左侧分类浏览，右侧预览资源。", 12, MUTED, false);
        status.setTextIsSelectable(true);
        status.setPadding(dp(2), dp(2), dp(6), dp(2));
        statusScroll.addView(status, new ScrollView.LayoutParams(-1, -2));
        LinearLayout.LayoutParams st = new LinearLayout.LayoutParams(-1, dp(64)); st.topMargin = dp(5); st.bottomMargin = dp(4); root.addView(statusScroll, st);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal); progress.setIndeterminate(true); progress.setVisibility(View.GONE); root.addView(progress, new LinearLayout.LayoutParams(-1, dp(3)));

        LinearLayout body = new LinearLayout(this); body.setOrientation(LinearLayout.HORIZONTAL); LinearLayout.LayoutParams bodyLp = new LinearLayout.LayoutParams(-1, 0, 1); bodyLp.topMargin = dp(7); root.addView(body, bodyLp);
        LinearLayout left = new LinearLayout(this); left.setOrientation(LinearLayout.VERTICAL); left.setPadding(dp(7), dp(7), dp(7), dp(7)); left.setBackgroundColor(PANEL);
        body.addView(left, new LinearLayout.LayoutParams(0, -1, 0.40f));
        TextView filesHeader = text("资源列表", 15, TEXT, true); left.addView(filesHeader, wrap());
        countText = text("尚未解包", 11, MUTED, false); left.addView(countText, wrap());
        HorizontalScrollView hsv = new HorizontalScrollView(this); hsv.setHorizontalScrollBarEnabled(false); categoryBar = new LinearLayout(this); categoryBar.setOrientation(LinearLayout.HORIZONTAL); hsv.addView(categoryBar); LinearLayout.LayoutParams h = new LinearLayout.LayoutParams(-1, -2); h.topMargin = dp(5); left.addView(hsv, h); addCategoryButtons();
        fileList = new ListView(this); fileList.setDividerHeight(dp(1)); fileList.setBackgroundColor(PANEL); left.addView(fileList, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout right = new LinearLayout(this); right.setOrientation(LinearLayout.VERTICAL); right.setPadding(dp(12), dp(10), dp(12), dp(10)); right.setBackgroundColor(PANEL);
        LinearLayout.LayoutParams rightLp = new LinearLayout.LayoutParams(0, -1, 0.60f); rightLp.leftMargin = dp(8); body.addView(right, rightLp);
        LinearLayout previewHead = new LinearLayout(this); previewHead.setOrientation(LinearLayout.HORIZONTAL); previewHead.setGravity(Gravity.CENTER_VERTICAL);
        previewTitle = text("资源预览", 16, TEXT, true); previewHead.addView(previewTitle, new LinearLayout.LayoutParams(0, -2, 1));
        exportSelectedButton = button("导出选中文件"); exportSelectedButton.setEnabled(false); previewHead.addView(exportSelectedButton, wrap()); right.addView(previewHead, wrap());
        previewImage = new ImageView(this); previewImage.setAdjustViewBounds(true); previewImage.setScaleType(ImageView.ScaleType.FIT_CENTER); previewImage.setVisibility(View.GONE);
        LinearLayout.LayoutParams imageLp = new LinearLayout.LayoutParams(-1, 0, 0.62f); imageLp.topMargin = dp(8); right.addView(previewImage, imageLp);
        ScrollView textScroll = new ScrollView(this); textScroll.setFillViewport(false); previewText = text("选择左侧文件查看内容。", 13, TEXT, false); previewText.setTypeface(Typeface.MONOSPACE); previewText.setPadding(dp(8), dp(8), dp(8), dp(8)); textScroll.addView(previewText); LinearLayout.LayoutParams textLp = new LinearLayout.LayoutParams(-1, 0, 0.38f); textLp.topMargin = dp(5); right.addView(textScroll, textLp);
        setContentView(root);
        chooseButton.setOnClickListener(v -> chooseNpk()); extractButton.setOnClickListener(v -> extract());
        saveButton.setOnClickListener(v -> createZipDocument()); exportSelectedButton.setOnClickListener(v -> createSelectedDocument());
        fileList.setOnItemClickListener((parent, view, position, id) -> { if (position >= 0 && position < shownFiles.size()) showFile(shownFiles.get(position)); });
    }

    private void addCategoryButtons() {
        String[] categories = {"全部", "贴图", "UI", "3D模型", "代码与配置", "音频", "其他"};
        categoryBar.removeAllViews();
        for (String c : categories) { Button b = button(c); b.setTextSize(12); b.setMinHeight(dp(44)); b.setMinimumHeight(dp(44)); b.setPadding(dp(12), 0, dp(12), 0); LinearLayout.LayoutParams p = wrap(); p.rightMargin = dp(5); categoryBar.addView(b, p); b.setOnClickListener(v -> { activeCategory = c; refreshList(); }); }
    }
    private TextView text(String s, int size, int color, boolean bold) { TextView t = new TextView(this); t.setText(s); t.setTextSize(size); t.setTextColor(color); if (bold) t.setTypeface(Typeface.DEFAULT, Typeface.BOLD); return t; }
    private Button button(String s) { Button b = new Button(this); b.setText(s); b.setTextSize(12); b.setTextColor(TEXT); b.setAllCaps(false); b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(PANEL2)); return b; }
    private LinearLayout.LayoutParams wrap() { return new LinearLayout.LayoutParams(-2, -2); }
    private int dp(int v) { return (int)(v * getResources().getDisplayMetrics().density + 0.5f); }

    private synchronized void ensurePathDict() throws Exception {
        if (pathDict == null) pathDict = new File(getFilesDir(), "pathdict.txt.gz");
        if (pathDict.exists() && pathDict.length() > 0) return;
        if (pathDict.exists() && !pathDict.delete()) throw new java.io.IOException("无法删除损坏的路径索引文件");
        Exception firstError = null;
        // Android normally preserves asset filenames exactly. Try both variants because
        // some previous CI workflows renamed the compressed path dictionary to pathdict.txt.
        String[] assetNames = {"pathdict.txt.gz", "pathdict.txt"};
        boolean copied = false;
        for (String assetName : assetNames) {
            try (InputStream in = getAssets().open(assetName); OutputStream fileOut = new FileOutputStream(pathDict);
                 OutputStream out = assetName.endsWith(".gz") ? fileOut : new GZIPOutputStream(fileOut)) {
                byte[] b = new byte[32768]; int n; while ((n = in.read(b)) > 0) out.write(b, 0, n);
                out.flush();
                copied = true;
                break;
            } catch (Exception e) {
                if (firstError == null) firstError = e;
                if (pathDict.exists()) pathDict.delete();
            }
        }
        if (!copied) throw new java.io.IOException("APK 内找不到路径索引。请确认 app/src/main/assets/pathdict.txt.gz 已提交到 GitHub 并打包进 APK。", firstError);
        if (!pathDict.exists() || pathDict.length() == 0) throw new java.io.IOException("路径索引文件为空");
    }
    private void chooseNpk() { Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT); i.addCategory(Intent.CATEGORY_OPENABLE); i.setType("*/*"); startActivityForResult(i, PICK_NPK); }
    private void createZipDocument() { if (zipFile == null || !zipFile.exists()) { status.setText("请先完成解包。"); return; } Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT); i.addCategory(Intent.CATEGORY_OPENABLE); i.setType("application/zip"); i.putExtra(Intent.EXTRA_TITLE, "NeoXLab-all-resources.zip"); startActivityForResult(i, CREATE_ZIP); }
    private void createSelectedDocument() { if (currentFile == null || !currentFile.isFile()) return; selectedExportFile = currentFile; Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT); i.addCategory(Intent.CATEGORY_OPENABLE); i.setType("application/octet-stream"); i.putExtra(Intent.EXTRA_TITLE, currentFile.getName()); startActivityForResult(i, CREATE_FILE); }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data); if (resultCode != RESULT_OK || data == null || data.getData() == null) return; Uri uri = data.getData();
        if (requestCode == PICK_NPK) { selectedUri = uri; status.setText("已选择：" + displayName(uri) + "。\n点击“开始解包”开始处理。详细日志可在此区域上下滑动查看。"); saveButton.setEnabled(false); }
        else if (requestCode == CREATE_ZIP) copyToUri(zipFile, uri, "ZIP 已保存到你选择的位置。");
        else if (requestCode == CREATE_FILE && selectedExportFile != null) copyToUri(selectedExportFile, uri, "已导出：" + selectedExportFile.getName());
    }
    private void copyToUri(File source, Uri target, String success) { worker.execute(() -> { try (InputStream in = new FileInputStream(source); OutputStream out = getContentResolver().openOutputStream(target)) { byte[] b = new byte[65536]; int n; while ((n = in.read(b)) > 0) out.write(b, 0, n); runOnUiThread(() -> status.setText(success)); } catch (Exception e) { runOnUiThread(() -> status.setText("保存失败：" + e.getMessage())); } }); }
    private String displayName(Uri uri) { String name = "selected.npk"; try (Cursor c = getContentResolver().query(uri, null, null, null, null)) { if (c != null && c.moveToFirst()) { int idx = c.getColumnIndex(OpenableColumns.DISPLAY_NAME); if (idx >= 0) name = c.getString(idx); } } catch (Exception ignored) {} return name; }

    private File ensureAstcDecoder() throws Exception {
        File decoder = new File(getFilesDir(), "astcenc");
        if (decoder.exists() && decoder.length() > 0 && decoder.canExecute()) return decoder;
        if (decoder.exists()) decoder.delete();
        try (InputStream in = getAssets().open("astcenc/arm64-v8a/astcenc");
             OutputStream out = new FileOutputStream(decoder)) {
            byte[] b = new byte[32768]; int n;
            while ((n = in.read(b)) > 0) out.write(b, 0, n);
        } catch (Exception e) {
            if (decoder.exists()) decoder.delete();
            throw new java.io.IOException("APK 内缺少 ASTC 解码器。请重新运行含 ASTC 构建步骤的 GitHub Actions。", e);
        }
        if (!decoder.setExecutable(true, true) || !decoder.canExecute()) {
            throw new java.io.IOException("无法设置 ASTC 解码器执行权限。");
        }
        return decoder;
    }

    private void extract() {
        if (selectedUri == null) { status.setText("请先选择 NPK 文件。"); return; }
        chooseButton.setEnabled(false); extractButton.setEnabled(false); saveButton.setEnabled(false); progress.setVisibility(View.VISIBLE); status.setText("正在复制文件并解析索引，请保持应用打开……");
        worker.execute(() -> { try {
            File input = new File(getCacheDir(), "selected.npk");
            try (InputStream in = getContentResolver().openInputStream(selectedUri); OutputStream out = new FileOutputStream(input)) { byte[] b = new byte[65536]; int n; while ((n = in.read(b)) > 0) out.write(b, 0, n); }
            ensurePathDict(); File astcDecoder = ensureAstcDecoder(); unpackDir = new File(getCacheDir(), "all_resources_out"); deleteTree(unpackDir); unpackDir.mkdirs();
            PyObject result = Python.getInstance().getModule("mobile_unpack").callAttr("extract_all_resources", input.getAbsolutePath(), unpackDir.getAbsolutePath(), pathDict.getAbsolutePath(), astcDecoder.getAbsolutePath());
            zipFile = new File(getCacheDir(), "NeoXLab-all-resources.zip"); if (zipFile.exists()) zipFile.delete(); zipDirectory(unpackDir, zipFile);
            runOnUiThread(() -> { scanFiles(); status.setText("解包完成：\n" + result.toString() + "\n左侧选择资源可预览；支持导出单个文件或全部 ZIP。"); saveButton.setEnabled(true); });
        } catch (Exception e) { runOnUiThread(() -> status.setText("解包失败：\n" + e.getMessage() + "\n此版本可能不支持该 NPK 的索引或加密方式。")); }
        finally { runOnUiThread(() -> { chooseButton.setEnabled(true); extractButton.setEnabled(true); progress.setVisibility(View.GONE); }); } });
    }
    private void scanFiles() { allFiles.clear(); collectFiles(unpackDir); refreshList(); }
    private void collectFiles(File dir) { File[] fs = dir == null ? null : dir.listFiles(); if (fs == null) return; for (File f : fs) { if (f.isDirectory()) collectFiles(f); else allFiles.add(f); } }
    private String category(File f) { String p = relative(f).toLowerCase(Locale.ROOT); String n = f.getName().toLowerCase(Locale.ROOT); if (p.contains("贴图") || p.contains("texture") || p.contains("image") || ends(n, ".png", ".jpg", ".jpeg", ".webp", ".ktx", ".astc", ".dds", ".tga", ".bmp")) return "贴图"; if (p.contains("ui") || p.contains("界面") || ends(n, ".atlas", ".sprite")) return "UI"; if (p.contains("模型") || p.contains("model") || ends(n, ".fbx", ".obj", ".gltf", ".glb", ".mesh", ".skel", ".skeleton")) return "3D模型"; if (p.contains("代码") || p.contains("config") || p.contains("script") || ends(n, ".lua", ".json", ".xml", ".js", ".py", ".txt", ".cfg", ".ini", ".yaml", ".yml", ".bytes")) return "代码与配置"; if (p.contains("audio") || p.contains("音频") || ends(n, ".wav", ".mp3", ".ogg", ".wem", ".bank", ".acb", ".awb")) return "音频"; if (p.contains("其他")) return "其他"; return "其他"; }
    private boolean ends(String s, String... suffixes) { for (String x : suffixes) if (s.endsWith(x)) return true; return false; }
    private String relative(File f) { if (unpackDir == null) return f.getName(); return unpackDir.toURI().relativize(f.toURI()).getPath(); }
    private void refreshList() { shownFiles.clear(); shownLabels.clear(); for (File f : allFiles) { if (activeCategory.equals("全部") || activeCategory.equals(category(f))) { shownFiles.add(f); shownLabels.add("[" + category(f) + "]  " + relative(f)); } } if (fileList != null) { ArrayAdapter<String> adapter = new ArrayAdapter<String>(this, android.R.layout.simple_list_item_1, shownLabels) { @Override public View getView(int pos, View cv, android.view.ViewGroup parent) { TextView t = (TextView) super.getView(pos, cv, parent); t.setTextColor(TEXT); t.setTextSize(11); t.setPadding(dp(7), dp(7), dp(7), dp(7)); t.setBackgroundColor(PANEL); return t; } }; fileList.setAdapter(adapter); } if (countText != null) countText.setText(shownFiles.size() + " / " + allFiles.size() + " 个文件 · " + activeCategory); }

    private void showFile(File f) { currentFile = f; exportSelectedButton.setEnabled(true); previewTitle.setText(f.getName()); previewImage.setVisibility(View.GONE); previewText.setVisibility(View.VISIBLE); previewText.setTextColor(TEXT);
        String ext = f.getName().toLowerCase(Locale.ROOT); long size = f.length(); String meta = "路径：" + relative(f) + "\n大小：" + humanSize(size) + "\n分类：" + category(f) + "\n格式：" + extension(f.getName()) + "\n\n";
        if (ends(ext, ".png", ".jpg", ".jpeg", ".webp", ".bmp")) { try { Bitmap bitmap = BitmapFactory.decodeFile(f.getAbsolutePath()); if (bitmap != null) { previewImage.setImageBitmap(bitmap); previewImage.setVisibility(View.VISIBLE); previewText.setText(meta + "图片预览已加载。\n尺寸：" + bitmap.getWidth() + " × " + bitmap.getHeight() + "\n支持的贴图会在解包时额外生成 PNG 预览图；原始资源也会保留。"); return; } } catch (Exception ignored) {} previewText.setText(meta + "图片解码失败。若这是压缩贴图，请检查解包目录中是否生成同名 PNG 预览图。"); return; }
        if (ends(ext, ".txt", ".json", ".xml", ".lua", ".js", ".py", ".cfg", ".ini", ".yaml", ".yml", ".md", ".csv", ".shader", ".glsl", ".html", ".css")) { try { byte[] bytes = readLimited(f, 1024 * 1024); String content = new String(bytes, Charset.forName("UTF-8")); previewText.setText(meta + content + (size > bytes.length ? "\n\n[预览已截断：文件超过 1 MB]" : "")); return; } catch (Exception e) { previewText.setText(meta + "文本读取失败：" + e.getMessage()); return; } }
        if (ends(ext, ".obj", ".fbx", ".gltf", ".glb", ".mesh", ".skel", ".skeleton", ".prefab", ".unity")) { previewText.setText(meta + "模型/场景资源已识别。当前版本提供文件信息与原始文件导出，但尚未集成通用 3D 渲染引擎，因此这里不能保证显示可旋转的模型画面。\n\n请点击“导出选中文件”保存模型原件。部分私有模型格式还需要专用解析器。"); return; }
        if (ends(ext, ".ktx", ".ktx2", ".astc", ".dds", ".pvr", ".tga")) { previewText.setText(meta + "已识别为贴图资源。若当前解码器支持此编码，解包时会在同目录生成 PNG 预览图，同时保留原始资源；不支持的编码仍可导出原文件。"); return; }
        previewText.setText(meta + "该格式暂无内置可视化预览。文件会保留在解包结果中，可以导出单个原始文件或导出全部 ZIP。\n\n文件头（前 64 字节）：\n" + hexHead(f));
    }
    private byte[] readLimited(File f, int max) throws Exception { try (InputStream in = new FileInputStream(f)) { byte[] b = new byte[(int)Math.min(f.length(), max)]; int off = 0, n; while (off < b.length && (n = in.read(b, off, b.length - off)) > 0) off += n; return off == b.length ? b : java.util.Arrays.copyOf(b, off); } }
    private String hexHead(File f) { StringBuilder s = new StringBuilder(); try (InputStream in = new FileInputStream(f)) { for (int i = 0; i < 64; i++) { int b = in.read(); if (b < 0) break; if (i > 0) s.append(' '); s.append(String.format(Locale.ROOT, "%02X", b)); } } catch (Exception e) { return "读取失败"; } return s.toString(); }
    private String extension(String name) { int i = name.lastIndexOf('.'); return i >= 0 ? name.substring(i + 1).toUpperCase(Locale.ROOT) : "无扩展名"; }
    private String humanSize(long n) { if (n < 1024) return n + " B"; if (n < 1024 * 1024) return String.format(Locale.ROOT, "%.1f KB", n / 1024.0); return String.format(Locale.ROOT, "%.2f MB", n / (1024.0 * 1024.0)); }
    private void zipDirectory(File root, File zip) throws Exception { try (ZipOutputStream zos = new ZipOutputStream(new FileOutputStream(zip))) { addToZip(root, root, zos); } }
    private void addToZip(File root, File file, ZipOutputStream zos) throws Exception { File[] children = file.listFiles(); if (children == null) return; for (File child : children) { if (child.isDirectory()) addToZip(root, child, zos); else { String name = root.toURI().relativize(child.toURI()).getPath(); zos.putNextEntry(new ZipEntry(name)); try (FileInputStream in = new FileInputStream(child)) { byte[] b = new byte[65536]; int n; while ((n = in.read(b)) > 0) zos.write(b, 0, n); } zos.closeEntry(); } } }
    private void deleteTree(File f) { if (f == null || !f.exists()) return; if (f.isDirectory()) { File[] children = f.listFiles(); if (children != null) for (File c : children) deleteTree(c); } f.delete(); }
    @Override protected void onDestroy() { super.onDestroy(); worker.shutdown(); }
}
