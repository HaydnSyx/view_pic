# View Pic - 大文件夹性能优化需求文档 v6.0

## 版本信息

- **版本**: v6.0.0  
- **创建日期**: 2026-01-12  
- **迭代主题**: 大文件夹图片加载性能优化（万张级图片支持）  
- **基于版本**: v5.0.0

---

## 项目概述

### 背景

在 v5.0 完成模块化拆分与日志功能接入后，当前应用在处理包含大量图片的文件夹时存在严重的性能问题：

#### 现存问题分析

1. **文件扫描阻塞**：
   - `image_service.list_images_in_folder()` 会一次性遍历文件夹内所有文件
   - 对于包含 1 万张以上图片的文件夹，文件扫描 + 排序耗时可达 1-3 秒
   - 整个图片列表存储在内存中（`self.images`），占用大量内存

2. **缩略图生成阻塞主线程**：
   - 当前实现在主线程中**同步生成**前 100 张图片的缩略图
   - 每张缩略图生成涉及文件 I/O、图像解码、缩放、base64 编码等操作
   - 100 张缩略图生成可能耗时 10-30 秒，期间应用完全无响应
   - macOS 可能弹出"应用无响应"提示，甚至被系统强制终止

3. **用户体验差**：
   - 点击文件夹后长时间白屏，无任何反馈
   - 无法取消加载操作
   - 无进度提示，用户不知道应用是否卡死

#### 性能优化目标

- ✅ **主线程永不阻塞**：所有耗时操作（文件扫描、缩略图生成）异步化
- ✅ **渐进式渲染**：缩略图生成完一张显示一张，提供流畅的视觉反馈
- ✅ **内存可控**：限制初次加载的图片数量，支持按需分页加载
- ✅ **用户可控**：提供加载状态指示器，支持取消当前加载任务
- ✅ **支持万张级文件夹**：目标性能基准：1 万张图片的文件夹，2 秒内显示前 50 张缩略图

---

## 六期核心需求

### 1. 文件扫描分页加载机制

#### 1.1 需求描述

- 文件扫描不再一次性返回所有图片，改为**分页加载**机制
- 初次加载仅返回前 N 张（建议 200-500 张），后续按需加载更多

#### 1.2 技术实现要点

- **修改 `image_service.list_images_in_folder()`**：
  - 新增参数：`offset: int = 0`, `limit: int = 500`
  - 使用生成器或分批遍历文件夹，避免一次性读取所有文件
  - 返回值包含：`images: List[Path]`, `total_count: int`, `has_more: bool`

- **修改 `ImageViewerApp.load_folder()`**：
  - 首次加载文件夹时只获取前 500 张图片路径
  - 在 UI 底部增加"加载更多"按钮（当 `has_more=True` 时显示）
  - 点击"加载更多"后追加下一批图片到 `self.images`

#### 1.3 配置参数（新增到 `settings.py`）

```python
# 性能优化相关配置
INITIAL_IMAGE_LOAD_LIMIT = 500  # 初次加载图片数量上限
LOAD_MORE_BATCH_SIZE = 200      # "加载更多"每次追加数量
```

---

### 2. 异步缩略图生成（线程池）

#### 2.1 需求描述

- 缩略图生成必须**完全异步化**，不能阻塞主线程
- 使用线程池并发生成多个缩略图，提升整体速度

#### 2.2 技术实现要点

- **新增异步服务模块 `src/services/async_thumbnail_service.py`**：
  ```python
  from concurrent.futures import ThreadPoolExecutor
  from typing import Callable, Optional
  
  class AsyncThumbnailService:
      def __init__(self, max_workers: int = 4):
          self.executor = ThreadPoolExecutor(max_workers=max_workers)
          self.current_task_id: Optional[str] = None
          
      def generate_thumbnails_async(
          self, 
          images: List[Path], 
          on_complete: Callable[[int, str], None],  # (index, data_uri)
          on_all_done: Callable[[], None],
          task_id: str
      ):
          """异步生成缩略图，每完成一张调用 on_complete 回调"""
          self.current_task_id = task_id
          # 提交任务到线程池...
          
      def cancel_current_task(self):
          """取消当前任务"""
          self.current_task_id = None
  ```

- **修改 `image_gallery._build_grid_view()`**：
  - 初始渲染时显示占位符（灰色骨架屏或图标）
  - 启动异步缩略图生成任务
  - 每个缩略图生成完成后，通过回调更新对应位置的 UI

#### 2.3 配置参数（新增到 `settings.py`）

```python
THUMBNAIL_WORKER_THREADS = 4    # 缩略图生成线程池大小
INITIAL_THUMBNAIL_COUNT = 50    # 初次渲染立即生成的缩略图数量
```

---

### 3. 渐进式渲染机制

#### 3.1 需求描述

- 网格视图初次渲染时显示占位符
- 缩略图生成完一张就立即更新到界面（渐进式显示）
- 用户可以边等待边浏览已加载的图片

#### 3.2 技术实现要点

- **修改 `image_gallery._build_grid_view()`**：
  - 初始为每张图片创建一个容器，显示占位符（`ft.Icon` 或 `ft.ProgressRing`）
  - 为每个容器分配唯一 ID 或索引
  - 缩略图生成完成后，通过 `page.update()` 更新对应容器的内容

- **占位符设计**：
  - 使用灰色图标 `ft.icons.Icons.IMAGE` 或加载动画
  - 占位符大小与最终缩略图保持一致，避免布局抖动

#### 3.3 渲染优先级策略

- **优先渲染可视区域**：
  - 先生成前 20-30 张（用户最可能先看到的）
  - 然后按序生成剩余部分
  - 如用户滚动到底部，动态调整生成优先级（可选优化）

---

### 4. 加载状态指示器与取消机制

#### 4.1 需求描述

- 点击文件夹后立即显示"加载中"状态
- 显示加载进度（例如："正在加载 25/100 张图片"）
- 提供"取消"按钮，允许用户中断当前加载任务

#### 4.2 技术实现要点

- **新增加载状态组件**（位于图片展示区域顶部）：
  ```python
  loading_indicator = ft.Container(
      content=ft.Row([
          ft.ProgressRing(width=20, height=20),
          ft.Text("正在加载图片... (25/100)"),
          ft.TextButton("取消", on_click=self.cancel_loading)
      ]),
      padding=10,
      bgcolor="#FFF8E1",
      visible=False  # 默认隐藏
  )
  ```

- **状态管理**：
  - `ImageViewerApp` 增加状态字段：
    - `is_loading: bool = False`
    - `loading_task_id: str | None = None`
    - `loaded_count: int = 0`
    - `total_count: int = 0`
  
  - 加载开始时：
    - 设置 `is_loading = True`
    - 显示加载指示器
    - 生成唯一任务 ID（使用 UUID）
  
  - 加载完成或取消时：
    - 设置 `is_loading = False`
    - 隐藏加载指示器
    - 清空任务 ID

- **取消机制**：
  - 点击"取消"按钮后：
    - 调用 `async_thumbnail_service.cancel_current_task()`
    - 停止后续缩略图生成
    - 已生成的缩略图保留显示

---

### 5. 配置集中管理

#### 5.1 新增配置项（`settings.py`）

```python
# ==================== 性能优化配置 ====================

# 文件扫描配置
INITIAL_IMAGE_LOAD_LIMIT = 500      # 初次加载图片数量上限
LOAD_MORE_BATCH_SIZE = 200          # "加载更多"每次追加数量

# 缩略图生成配置
THUMBNAIL_WORKER_THREADS = 4        # 线程池大小（建议 2-8）
INITIAL_THUMBNAIL_COUNT = 50        # 首屏立即生成数量
THUMBNAIL_GENERATION_TIMEOUT = 5    # 单张缩略图生成超时（秒）

# 渲染配置
ENABLE_PROGRESSIVE_RENDERING = True  # 是否启用渐进式渲染
SHOW_LOADING_INDICATOR = True        # 是否显示加载指示器
```

---

## 技术实现方案（详细步骤）

### 阶段一：文件扫描优化（P0）

#### 步骤 1.1 - 修改 `image_service`

**文件**: `src/services/image_service.py`

```python
from dataclasses import dataclass
from typing import List
from pathlib import Path

@dataclass
class ImageBatchResult:
    """图片批次加载结果"""
    images: List[Path]          # 本批次图片列表
    total_count: int            # 文件夹内总图片数（估算值）
    has_more: bool              # 是否还有更多图片
    offset: int                 # 当前偏移量

def list_images_in_folder_batch(
    folder: Path, 
    supported_formats: tuple[str, ...],
    offset: int = 0,
    limit: int = 500
) -> ImageBatchResult:
    """分页扫描文件夹下的图片
    
    Args:
        folder: 文件夹路径
        supported_formats: 支持的图片格式
        offset: 偏移量
        limit: 本次最多返回数量
        
    Returns:
        ImageBatchResult: 包含图片列表、总数等信息
    """
    # 实现逻辑：
    # 1. 遍历文件夹，跳过前 offset 个文件
    # 2. 收集最多 limit 个符合条件的图片
    # 3. 粗略估算总数（可选：全扫一遍统计，或使用缓存）
    # 4. 返回结果
```

#### 步骤 1.2 - 修改 `ImageViewerApp.load_folder()`

**文件**: `src/app.py`

- 修改 `load_folder` 方法，首次调用 `list_images_in_folder_batch(offset=0, limit=500)`
- 将返回的 `ImageBatchResult` 存储到应用状态
- 如果 `has_more=True`，在图片区域底部显示"加载更多"按钮

#### 步骤 1.3 - 实现"加载更多"功能

**文件**: `src/app.py`

```python
def load_more_images(self, e: ft.ControlEvent):
    """加载下一批图片"""
    current_offset = len(self.images)
    batch_result = image_service.list_images_in_folder_batch(
        self.current_folder,
        self.supported_formats,
        offset=current_offset,
        limit=settings.LOAD_MORE_BATCH_SIZE
    )
    
    self.images.extend(batch_result.images)
    self.display_images()  # 重新渲染
```

#### 验收标准

- ✅ 点击包含 1 万张图片的文件夹，1 秒内完成文件扫描（只返回前 500 张）
- ✅ 内存占用：初次加载仅保存 500 个 Path 对象
- ✅ "加载更多"按钮功能正常，点击后追加下一批图片
- ✅ 日志记录：文件扫描耗时、实际返回数量

---

### 阶段二：异步缩略图生成（P0）

#### 步骤 2.1 - 创建异步缩略图服务

**新建文件**: `src/services/async_thumbnail_service.py`

```python
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Callable, List, Optional
from loguru import logger
from src.services import image_service
from src.config import settings

class AsyncThumbnailService:
    """异步缩略图生成服务"""
    
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.current_task_id: Optional[str] = None
        self.futures: List[Future] = []
        
    def generate_thumbnails_async(
        self,
        images: List[Path],
        thumbnail_size: int,
        on_single_complete: Callable[[int, str], None],
        on_all_complete: Callable[[], None],
        task_id: str
    ):
        """异步生成缩略图
        
        Args:
            images: 图片路径列表
            thumbnail_size: 缩略图尺寸
            on_single_complete: 单张完成回调 (index, data_uri)
            on_all_complete: 全部完成回调
            task_id: 任务唯一ID
        """
        self.current_task_id = task_id
        self.futures.clear()
        
        def process_image(index: int, image_path: Path):
            """处理单张图片"""
            if self.current_task_id != task_id:
                return None  # 任务已取消
                
            try:
                data_uri = image_service.create_thumbnail_data_uri(
                    image_path, thumbnail_size
                )
                return (index, data_uri)
            except Exception as exc:
                logger.error("缩略图生成失败: {}, {}", image_path, exc)
                return None
        
        # 提交所有任务
        for idx, img_path in enumerate(images):
            future = self.executor.submit(process_image, idx, img_path)
            future.add_done_callback(
                lambda f, i=idx: self._on_thumbnail_done(f, i, on_single_complete)
            )
            self.futures.append(future)
            
        # 等待所有任务完成
        def wait_all():
            for future in self.futures:
                future.result()  # 阻塞等待
            if self.current_task_id == task_id:
                on_all_complete()
        
        self.executor.submit(wait_all)
        
    def _on_thumbnail_done(
        self, 
        future: Future, 
        index: int, 
        callback: Callable[[int, str], None]
    ):
        """单张缩略图完成的回调"""
        result = future.result()
        if result:
            idx, data_uri = result
            callback(idx, data_uri)
            
    def cancel_current_task(self):
        """取消当前任务"""
        logger.info("取消当前缩略图生成任务: {}", self.current_task_id)
        self.current_task_id = None
        # 注意：已提交的 Future 无法真正取消，但可以通过 task_id 判断跳过
        
    def shutdown(self):
        """关闭线程池"""
        self.executor.shutdown(wait=False)
```

#### 步骤 2.2 - 修改 `image_gallery` 支持异步渲染

**文件**: `src/core/image_gallery.py`

- 修改 `_build_grid_view()` 函数：
  - 初始渲染时创建占位符容器
  - 返回容器列表 + 启动异步生成任务

```python
def _build_grid_view_async(
    images: List[Path],
    window_width: float,
    on_preview: Callable[[int], None],
    on_thumbnail_ready: Callable[[int, ft.Container], None],  # 新增回调
) -> ft.GridView:
    """构建网格视图（支持异步加载）"""
    
    # ... 计算列数等逻辑
    
    grid = ft.GridView(...)
    
    # 创建占位符容器
    for idx, image_path in enumerate(images[:100]):
        placeholder = ft.Container(
            content=ft.Column([
                ft.Icon(
                    ft.icons.Icons.IMAGE,
                    size=thumbnail_size,
                    color="#CCCCCC"
                ),
                ft.Text(
                    image_path.name,
                    size=12,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
            ]),
            on_click=lambda e, i=idx: on_preview(i),
            data=idx,  # 存储索引，用于后续更新
        )
        grid.controls.append(placeholder)
    
    return grid
```

#### 步骤 2.3 - 修改 `ImageViewerApp` 集成异步服务

**文件**: `src/app.py`

```python
from src.services.async_thumbnail_service import AsyncThumbnailService
import uuid

class ImageViewerApp:
    def __init__(self):
        # ... 现有初始化
        self.async_thumbnail_service = AsyncThumbnailService(
            max_workers=settings.THUMBNAIL_WORKER_THREADS
        )
        self.current_loading_task_id: Optional[str] = None
        
    def display_images(self):
        """显示图片列表（异步版本）"""
        # 先渲染占位符
        grid = image_gallery._build_grid_view_async(...)
        self.image_display.controls.append(grid)
        self.page.update()
        
        # 启动异步缩略图生成
        task_id = str(uuid.uuid4())
        self.current_loading_task_id = task_id
        
        self.async_thumbnail_service.generate_thumbnails_async(
            images=self.images[:100],
            thumbnail_size=settings.GRID_THUMBNAIL_SIZE,
            on_single_complete=self._on_thumbnail_complete,
            on_all_complete=self._on_all_thumbnails_complete,
            task_id=task_id
        )
        
    def _on_thumbnail_complete(self, index: int, data_uri: str):
        """单张缩略图完成回调"""
        # 更新对应位置的容器
        # 注意：需要在主线程中调用 page.update()
        # Flet 的线程安全需要特殊处理
        pass
        
    def _on_all_thumbnails_complete(self):
        """所有缩略图完成回调"""
        logger.info("所有缩略图生成完成")
```

#### 验收标准

- ✅ 点击文件夹后立即显示占位符，应用不卡顿
- ✅ 缩略图在后台生成，逐个显示到界面
- ✅ 使用 4 个线程并发生成，整体速度提升 3-4 倍
- ✅ 日志记录：每张缩略图生成耗时、总耗时

---

### 阶段三：渐进式渲染与加载状态（P0）

#### 步骤 3.1 - 实现占位符到真实缩略图的替换

**技术难点**：Flet 的线程安全问题

- Flet 要求所有 UI 更新在主线程进行
- 需要使用 `page.run_thread_safe()` 或消息队列机制

```python
def _on_thumbnail_complete(self, index: int, data_uri: str):
    """单张缩略图完成回调（异步线程中调用）"""
    
    def update_ui():
        # 在主线程中执行
        grid = self.image_display.controls[0]  # 假设 grid 是第一个控件
        if index < len(grid.controls):
            container = grid.controls[index]
            # 更新容器内容
            container.content = ft.Column([
                ft.Image(
                    src=data_uri,
                    width=settings.GRID_THUMBNAIL_SIZE,
                    height=settings.GRID_THUMBNAIL_SIZE,
                    fit=ft.BoxFit.COVER,
                ),
                ft.Text(self.images[index].name, ...)
            ])
            self.page.update()
    
    # 调度到主线程
    self.page.run_thread_safe(update_ui)
```

#### 步骤 3.2 - 实现加载状态指示器

**文件**: `src/app.py`

```python
def create_loading_indicator(self) -> ft.Container:
    """创建加载状态指示器"""
    self.loading_progress_text = ft.Text("正在加载图片... (0/0)")
    
    return ft.Container(
        content=ft.Row([
            ft.ProgressRing(width=20, height=20, stroke_width=2),
            self.loading_progress_text,
            ft.TextButton(
                "取消",
                on_click=self.cancel_loading,
                icon=ft.icons.Icons.CANCEL
            )
        ], spacing=10),
        padding=10,
        bgcolor="#FFF3E0",
        border_radius=8,
        visible=False,
        ref=ft.Ref[ft.Container]()
    )

def show_loading_indicator(self, total: int):
    """显示加载指示器"""
    self.loading_indicator.visible = True
    self.loaded_count = 0
    self.total_count = total
    self.update_loading_progress()
    
def update_loading_progress(self):
    """更新加载进度"""
    self.loading_progress_text.value = (
        f"正在加载图片... ({self.loaded_count}/{self.total_count})"
    )
    self.page.update()
    
def hide_loading_indicator(self):
    """隐藏加载指示器"""
    self.loading_indicator.visible = False
    self.page.update()
    
def cancel_loading(self, e: ft.ControlEvent):
    """取消加载"""
    logger.info("用户取消加载")
    self.async_thumbnail_service.cancel_current_task()
    self.hide_loading_indicator()
```

#### 验收标准

- ✅ 加载开始时显示指示器："正在加载图片... (0/100)"
- ✅ 每完成一张缩略图，进度数字实时更新
- ✅ 点击"取消"后停止后续生成，已完成的保留
- ✅ 所有缩略图完成后自动隐藏指示器

---

### 阶段四：配置与日志完善（P1）

#### 步骤 4.1 - 更新 `settings.py`

添加所有新增配置项（见上文配置集中管理章节）

#### 步骤 4.2 - 增加关键日志打点

- 文件扫描开始/结束、耗时
- 缩略图生成开始/结束、总耗时、平均速度
- 用户取消操作
- 异常情况（文件读取失败、超时等）

---

## 测试与验收

### 性能测试场景

#### 场景 1：小文件夹（< 100 张）
- **操作**：点击包含 50 张图片的文件夹
- **预期**：
  - 1 秒内显示所有占位符
  - 3-5 秒内所有缩略图生成完毕

#### 场景 2：中等文件夹（500-1000 张）
- **操作**：点击包含 800 张图片的文件夹
- **预期**：
  - 1 秒内显示前 100 个占位符
  - 5-10 秒内前 100 张缩略图生成完毕
  - 内存占用稳定（< 500 MB）

#### 场景 3：大文件夹（1 万张以上）⭐ 核心场景
- **操作**：点击包含 10,000 张图片的文件夹
- **预期**：
  - **2 秒内**显示前 100 个占位符（文件扫描 500 张 + 渲染占位符）
  - **10 秒内**前 50 张缩略图显示完毕
  - **30 秒内**前 100 张缩略图全部显示
  - 应用全程响应，无卡顿、无系统强制终止
  - CPU 占用：多核并行，单核不超过 80%
  - 内存占用：< 800 MB

#### 场景 4：取消加载
- **操作**：点击包含 5000 张图片的文件夹，等待 3 秒后点击"取消"
- **预期**：
  - 立即停止后续缩略图生成
  - 已生成的缩略图保留显示
  - 加载指示器消失

---

### 功能回归测试

- ✅ 视图模式切换（网格/列表）功能正常
- ✅ 大图预览功能正常
- ✅ 键盘快捷键（左右箭头、ESC 等）正常
- ✅ 文件夹树展开/收起功能正常
- ✅ 移动设备监控功能正常
- ✅ 日志记录完整、格式正确

---

## 实现优先级

### P0（本期必须完成）

1. ✅ **文件扫描分页加载**：修改 `image_service`，支持 offset/limit 参数
2. ✅ **异步缩略图生成**：创建 `AsyncThumbnailService`，使用线程池
3. ✅ **渐进式渲染**：占位符 → 真实缩略图的逐个替换
4. ✅ **加载状态指示器**：显示进度、支持取消
5. ✅ **性能测试**：验证 1 万张图片场景不卡顿

### P1（建议尽快完成）

1. 缩略图磁盘缓存（避免重复生成）
2. 智能优先级渲染（可视区域优先）
3. 虚拟滚动（真正的无限加载）

### P2（后续优化）

1. 预加载策略（预判用户滚动方向）
2. WebP 格式缩略图（更小体积）
3. 多级缩略图（不同尺寸）

---

## 风险评估与注意事项

### 技术风险

1. **Flet 线程安全问题**：
   - Flet 的 UI 更新必须在主线程
   - 需使用 `page.run_thread_safe()` 或类似机制
   - 建议：先小规模测试，确保无死锁或崩溃

2. **内存管理**：
   - base64 编码的缩略图占用内存较大
   - 建议：限制同时在内存中的缩略图数量（如只保留 200 张）
   - 超出部分可以卸载（清空 Image.src），滚动回来时重新加载

3. **文件系统兼容性**：
   - macOS、Windows 文件系统特性不同
   - 需测试跨平台兼容性（如文件排序、权限处理）

### 向后兼容性

- ✅ 保持现有 API 签名兼容（或通过参数默认值兼容）
- ✅ 不影响现有功能（预览、键盘、设备监控等）

---

## 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|----------|------|
| v6.0.0 | 2026-01-12 | 六期需求：大文件夹性能优化（万张级图片支持） | AI Assistant |
