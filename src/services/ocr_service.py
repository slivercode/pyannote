"""
OCR 字幕提取服务
基于 PaddleOCR 实现视频字幕识别和提取
"""
import os
import cv2
import time
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import numpy as np
from datetime import datetime

from models.ocr_models import (
    OCRConfig, SubtitleItem, OCRProgress, OCRResult, 
    VideoInfo, SubtitleRegion, SystemResourceInfo
)


class OCRService:
    """OCR 字幕提取服务类"""
    
    def __init__(self):
        self.ocr_engine = None
        self.is_initialized = False
        self.supported_languages = {
            'ch': '中文简体', 'en': '英文', 'ja': '日文', 'ko': '韩文',
            'fr': '法文', 'de': '德文', 'es': '西班牙文', 'ru': '俄文',
            'ar': '阿拉伯文', 'hi': '印地文', 'th': '泰文', 'vi': '越南文'
        }
        
    def initialize_ocr(self, config: OCRConfig) -> bool:
        """初始化OCR引擎"""
        try:
            # 延迟导入PaddleOCR以避免启动时的依赖问题
            from paddleocr import PaddleOCR
            
            # 检查GPU可用性
            gpu_actually_available = False
            if config.use_gpu:
                try:
                    import paddle
                    gpu_actually_available = paddle.is_compiled_with_cuda()
                    if not gpu_actually_available:
                        print("⚠️ 用户请求GPU加速，但PaddlePaddle未编译CUDA支持")
                        print("   将自动降级到CPU模式")
                except Exception as e:
                    print(f"⚠️ 无法检测GPU状态: {e}")
                    print("   将使用CPU模式")
            
            # 根据实际情况决定是否使用GPU
            use_gpu_final = config.use_gpu and gpu_actually_available
            
            # PaddleOCR 3.x 使用 device 参数而不是 use_gpu
            # device='gpu' 表示使用GPU，device='cpu' 表示使用CPU
            # 注意：3.x版本不支持 show_log 参数
            ocr_kwargs = {
                'lang': config.language,
                'device': 'gpu' if use_gpu_final else 'cpu',
                # ========== 性能优化参数 ==========
                'rec_batch_num': 6,          # 每张图同时识别6个文本框（批处理）
                'use_angle_cls': False,      # 禁用角度分类（字幕通常是水平的）
                # ==================================
            }
            
            print(f"\n{'='*60}")
            print(f"正在初始化OCR引擎...")
            print(f"  语言: {config.language}")
            print(f"  用户选择: {'GPU加速' if config.use_gpu else 'CPU模式'}")
            print(f"  实际使用: {'GPU加速' if use_gpu_final else 'CPU模式'}")
            
            if config.use_gpu and not use_gpu_final:
                print(f"  ⚠️ GPU不可用，已自动切换到CPU模式")
            
            self.ocr_engine = PaddleOCR(**ocr_kwargs)
            self.is_initialized = True
            
            # 确认实际使用的设备
            try:
                import paddle
                if paddle.is_compiled_with_cuda() and use_gpu_final:
                    print(f"✅ OCR引擎初始化成功 - 使用GPU加速")
                else:
                    print(f"✅ OCR引擎初始化成功 - 使用CPU模式")
            except:
                print(f"✅ OCR引擎初始化成功")
            
            print(f"{'='*60}\n")
            return True
            
        except Exception as e:
            print(f"\n{'='*60}")
            print(f"❌ OCR引擎初始化失败: {e}")
            print(f"{'='*60}\n")
            import traceback
            traceback.print_exc()
            return False
            traceback.print_exc()
            return False
    
    def get_video_info(self, video_path: str) -> Optional[VideoInfo]:
        """获取视频文件信息"""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
                
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0
            
            cap.release()
            
            file_size = os.path.getsize(video_path)
            file_format = Path(video_path).suffix.lower()
            
            return VideoInfo(
                filename=Path(video_path).name,
                duration=duration,
                width=width,
                height=height,
                fps=fps,
                size=file_size,
                format=file_format
            )
        except Exception as e:
            print(f"获取视频信息失败: {e}")
            return None
    
    def detect_subtitle_regions(self, frame: np.ndarray) -> List[SubtitleRegion]:
        """自动检测字幕区域"""
        h, w = frame.shape[:2]
        regions = []
        
        # 策略1: 下半部分（最常见，优先级最高）
        regions.append(SubtitleRegion(
            x=0, 
            y=int(h * 0.5), 
            width=w, 
            height=int(h * 0.5),
            name="下半部分"
        ))
        
        # 策略2: 底部1/4区域
        regions.append(SubtitleRegion(
            x=0, 
            y=int(h * 0.75), 
            width=w, 
            height=int(h * 0.25),
            name="底部区域"
        ))
        
        # 策略3: 全屏扫描（最后尝试）
        regions.append(SubtitleRegion(
            x=0, 
            y=0, 
            width=w, 
            height=h,
            name="全屏区域"
        ))
        
        return regions
    
    def enhance_frame_for_ocr(self, frame: np.ndarray) -> List[np.ndarray]:
        """增强帧图像以提高OCR识别率 - 优化版本，包含多种有效方法"""
        try:
            # 转换为灰度图
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame.copy()
            
            enhanced_versions = []
            
            # 方法1: 原始彩色图（保持最高质量）
            enhanced_versions.append(frame.copy())
            
            # 方法2: 高质量灰度图
            enhanced_versions.append(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
            
            # 方法3: CLAHE增强（对比度限制自适应直方图均衡化）
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            enhanced_clahe = clahe.apply(gray)
            enhanced_versions.append(cv2.cvtColor(enhanced_clahe, cv2.COLOR_GRAY2BGR))
            
            # 方法4: 二值化（Otsu自动阈值）
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            enhanced_versions.append(cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR))
            
            # 方法5: 反色二值化（适合白底黑字的情况）
            _, binary_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            enhanced_versions.append(cv2.cvtColor(binary_inv, cv2.COLOR_GRAY2BGR))
            
            return enhanced_versions
            
        except Exception as e:
            # 如果增强失败，返回原始帧
            return [frame]
    def extract_frames(self, video_path: str, subtitle_region: Optional[SubtitleRegion] = None, 
                      mode: str = "auto") -> List[Tuple[int, np.ndarray, float]]:
        """
        提取视频帧用于OCR识别 - 动态间隔版本
        
        根据识别模式动态调整帧提取策略：
        - fast: 每秒提取1帧 (适合快速预览)
        - auto/balanced: 每秒提取2帧 (平衡速度和准确度)
        - precise: 每秒提取4帧 (最高精度)
        
        这样可以根据视频FPS自动适配，而不是固定间隔
        """
        frames = []
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            print(f"无法打开视频文件: {video_path}")
            return frames
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # 根据模式动态计算帧间隔
        if mode == "fast":
            frames_per_second = 1  # 每秒1帧
        elif mode == "precise":
            frames_per_second = 4  # 每秒4帧
        else:  # auto/balanced
            frames_per_second = 2  # 每秒2帧
        
        frame_interval = max(1, int(fps / frames_per_second))
        frame_index = 0
        
        print(f"视频信息: FPS={fps}, 总帧数={total_frames}")
        print(f"识别模式: {mode}, 每秒提取{frames_per_second}帧, 帧间隔={frame_interval}")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            if frame_index % frame_interval == 0:
                timestamp = frame_index / fps
                
                # 如果指定了字幕区域，则裁剪帧
                if subtitle_region:
                    h, w = frame.shape[:2]
                    x1 = max(0, subtitle_region.x)
                    y1 = max(0, subtitle_region.y)
                    x2 = min(w, subtitle_region.x + subtitle_region.width)
                    y2 = min(h, subtitle_region.y + subtitle_region.height)
                    cropped_frame = frame[y1:y2, x1:x2]
                    
                    # 检查裁剪后的帧是否有效
                    if cropped_frame.shape[0] > 0 and cropped_frame.shape[1] > 0:
                        frames.append((frame_index, cropped_frame, timestamp))
                else:
                    # 不指定区域时，保存完整帧，后续会尝试多个区域
                    frames.append((frame_index, frame, timestamp))
            
            frame_index += 1
        
        cap.release()
        print(f"总共提取了 {len(frames)} 帧")
        return frames
    
    def recognize_text_with_multiple_strategies(self, frame: np.ndarray, config: OCRConfig) -> List[Dict[str, Any]]:
        """使用多种策略识别文字 - 优化版本"""
        all_results = []
        
        # 只测试最有效的字幕区域
        h, w = frame.shape[:2]
        
        # 优先级排序的区域
        priority_regions = [
            ("下半部分", (0, int(h * 0.5), w, int(h * 0.5))),
            ("底部区域", (0, int(h * 0.75), w, int(h * 0.25)))
        ]
        
        for region_name, (x, y, width, height) in priority_regions:
            # 裁剪区域
            cropped_frame = frame[y:y+height, x:x+width]
            
            if cropped_frame.shape[0] <= 0 or cropped_frame.shape[1] <= 0:
                continue
            
            # 尝试多种增强方法
            enhanced_frames = self.enhance_frame_for_ocr(cropped_frame)
            
            for i, enhanced_frame in enumerate(enhanced_frames):
                results = self.recognize_text_in_frame(enhanced_frame, config)
                
                for result in results:
                    result['region'] = region_name
                    result['method'] = i+1
                    all_results.append(result)
                
                # 如果找到结果，可以提前停止（可选）
                if results and len(all_results) >= 3:
                    break
            
            # 如果已经找到足够的结果，停止尝试其他区域
            if len(all_results) >= 3:
                break
        
        # 去重和排序
        unique_results = []
        seen_texts = set()
        
        for result in all_results:
            text_key = result['text'].strip().lower()
            if text_key not in seen_texts and len(text_key) > 0:
                seen_texts.add(text_key)
                unique_results.append(result)
        
        # 按置信度排序
        unique_results.sort(key=lambda x: x['confidence'], reverse=True)
        
        return unique_results
    
    def recognize_text_in_frame(self, frame: np.ndarray, config: OCRConfig) -> List[Dict[str, Any]]:
        """在单帧中识别文字"""
        if not self.is_initialized or not self.ocr_engine:
            return []
            
        try:
            # PaddleOCR 3.x 使用predict方法
            results = self.ocr_engine.predict(frame)
            
            if not results:
                return []
            
            recognized_texts = []
            
            # 处理PaddleOCR结果 - 尝试多种格式
            for i, result in enumerate(results):
                try:
                    # 方法1: 如果是字典格式
                    if isinstance(result, dict):
                        # 尝试不同的键名
                        texts = result.get('rec_texts') or result.get('text') or result.get('texts', [])
                        scores = result.get('rec_scores') or result.get('confidence') or result.get('scores', [])
                        polys = result.get('rec_polys') or result.get('bbox') or result.get('polys', [])
                        
                        if isinstance(texts, str):
                            texts = [texts]
                        if isinstance(scores, (int, float)):
                            scores = [scores]
                        
                        for j, (text, score) in enumerate(zip(texts, scores)):
                            if score >= config.confidence_threshold and text.strip():
                                bbox = []
                                if j < len(polys):
                                    bbox = polys[j].tolist() if hasattr(polys[j], 'tolist') else polys[j]
                                
                                recognized_texts.append({
                                    'text': text.strip(),
                                    'confidence': float(score),
                                    'bbox': bbox
                                })
                    
                    # 方法2: 如果是列表格式 [bbox, (text, confidence)]
                    elif isinstance(result, (list, tuple)) and len(result) >= 2:
                        bbox = result[0] if len(result) > 0 else []
                        text_info = result[1] if len(result) > 1 else None
                        
                        if text_info and isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                            text = text_info[0]
                            confidence = text_info[1]
                            
                            if confidence >= config.confidence_threshold and text.strip():
                                recognized_texts.append({
                                    'text': text.strip(),
                                    'confidence': float(confidence),
                                    'bbox': bbox
                                })
                    
                    # 方法3: 如果有属性访问
                    else:
                        # 尝试直接访问属性
                        if hasattr(result, 'text') and hasattr(result, 'confidence'):
                            text = result.text
                            confidence = result.confidence
                            bbox = getattr(result, 'bbox', [])
                            
                            if confidence >= config.confidence_threshold and text.strip():
                                recognized_texts.append({
                                    'text': text.strip(),
                                    'confidence': float(confidence),
                                    'bbox': bbox
                                })
                    
                except Exception as e:
                    continue
            
            return recognized_texts
            
        except Exception as e:
            print(f"文字识别失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def process_video_ocr(self, video_path: str, config: OCRConfig, 
                         subtitle_region: Optional[SubtitleRegion] = None,
                         progress_callback=None) -> OCRResult:
        """处理视频OCR提取"""
        start_time = time.time()
        
        # 初始化OCR引擎
        if not self.initialize_ocr(config):
            raise Exception("OCR引擎初始化失败")
        
        # 获取视频信息
        video_info = self.get_video_info(video_path)
        if not video_info:
            raise Exception("无法获取视频信息")
        
        # 提取帧
        if progress_callback:
            progress_callback(OCRProgress(
                stage="extracting",
                progress=0,
                current_frame=0,
                total_frames=0,
                message="正在提取视频帧..."
            ))
        
        # 使用识别模式动态提取帧，而不是固定间隔
        frames = self.extract_frames(video_path, subtitle_region, mode=config.mode)
        total_frames = len(frames)
        
        if total_frames == 0:
            raise Exception("未能提取到有效帧")
        
        # OCR识别
        subtitles = []
        processed_frames = 0
        
        for frame_index, frame, timestamp in frames:
            if progress_callback:
                progress = 50 + (processed_frames / total_frames) * 50
                progress_callback(OCRProgress(
                    stage="recognizing",
                    progress=progress,
                    current_frame=processed_frames,
                    total_frames=total_frames,
                    message=f"正在识别第 {processed_frames + 1}/{total_frames} 帧..."
                ))
            
            # 每10帧输出一次进度
            if processed_frames % 10 == 0:
                print(f"进度: {processed_frames}/{total_frames} 帧 ({progress:.1f}%)")
            
            # 使用多策略识别
            if subtitle_region:
                # 如果指定了区域，使用传统方法
                texts = self.recognize_text_in_frame(frame, config)
            else:
                # 如果没有指定区域，使用多策略方法
                texts = self.recognize_text_with_multiple_strategies(frame, config)
            
            for text_info in texts:
                subtitle = SubtitleItem(
                    start_time=timestamp,
                    end_time=timestamp + 1.0,  # 默认1秒持续时间
                    text=text_info['text'],
                    confidence=text_info['confidence'],
                    frame_index=frame_index
                )
                subtitles.append(subtitle)
            
            processed_frames += 1
        
        # 后处理：去重、合并、过滤
        print(f"\n后处理: 原始字幕数 {len(subtitles)}")
        
        if config.remove_duplicates:
            subtitles = self._remove_duplicate_subtitles(subtitles)
            print(f"去重后: {len(subtitles)} 条")
        
        if config.filter_watermark:
            subtitles = self._filter_watermark_subtitles(subtitles)
            print(f"过滤水印后: {len(subtitles)} 条")
        
        subtitles = self._merge_continuous_subtitles(subtitles)
        print(f"合并后: {len(subtitles)} 条")
        
        processing_time = time.time() - start_time
        
        print(f"\n✅ OCR处理完成!")
        print(f"总耗时: {processing_time:.2f}秒")
        print(f"识别到 {len(subtitles)} 条字幕")
        
        return OCRResult(
            video_file=Path(video_path).name,
            subtitles=subtitles,
            total_duration=video_info.duration,
            processing_time=processing_time
        )
    
    def _remove_duplicate_subtitles(self, subtitles: List[SubtitleItem]) -> List[SubtitleItem]:
        """去除连续重复的字幕，保留有时间间隔的重复"""
        if not subtitles:
            return subtitles
        
        # 按时间排序
        sorted_subtitles = sorted(subtitles, key=lambda x: x.start_time)
        
        unique_subtitles = []
        prev_text = None
        prev_time = None
        
        for subtitle in sorted_subtitles:
            text_key = subtitle.text.strip().lower()
            
            # 跳过空文本
            if len(text_key) == 0:
                continue
            
            # 如果文本与前一条不同，或者时间间隔超过5秒，则保留
            if prev_text != text_key or (prev_time and subtitle.start_time - prev_time > 5.0):
                unique_subtitles.append(subtitle)
                prev_text = text_key
                prev_time = subtitle.start_time
            # 否则是连续重复，跳过
        
        return unique_subtitles
    
    def _filter_watermark_subtitles(self, subtitles: List[SubtitleItem]) -> List[SubtitleItem]:
        """过滤水印字幕 - 改进版"""
        if not subtitles:
            return subtitles
        
        text_counts = {}
        text_positions = {}  # 记录每个文本出现的时间位置
        
        for subtitle in subtitles:
            text = subtitle.text.strip()
            text_counts[text] = text_counts.get(text, 0) + 1
            
            if text not in text_positions:
                text_positions[text] = []
            text_positions[text].append(subtitle.start_time)
        
        total_count = len(subtitles)
        
        # 改进的水印检测规则：
        # 1. 出现次数超过总数的50%（提高阈值）
        # 2. 且文本长度小于等于3个字符（短文本更可能是水印）
        # 3. 且在视频中分布均匀（不是集中在某一段）
        
        watermark_texts = set()
        
        for text, count in text_counts.items():
            # 规则1: 出现频率过高
            if count > total_count * 0.5:
                # 规则2: 短文本
                if len(text) <= 3:
                    watermark_texts.add(text)
                # 规则3: 即使是长文本，如果出现次数超过70%也标记
                elif count > total_count * 0.7:
                    # 检查是否分布均匀
                    positions = sorted(text_positions[text])
                    if len(positions) >= 3:
                        # 计算时间间隔的标准差，如果很小说明分布均匀
                        intervals = [positions[i+1] - positions[i] for i in range(len(positions)-1)]
                        if intervals:
                            avg_interval = sum(intervals) / len(intervals)
                            # 如果间隔都很接近平均值，说明是均匀分布的水印
                            variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
                            if variance < avg_interval * 0.5:  # 方差小于平均值的50%
                                watermark_texts.add(text)
        
        # 标记水印
        filtered_subtitles = []
        for subtitle in subtitles:
            text = subtitle.text.strip()
            if text in watermark_texts:
                subtitle.is_watermark = True
            filtered_subtitles.append(subtitle)
        
        return filtered_subtitles
    
    def _merge_continuous_subtitles(self, subtitles: List[SubtitleItem]) -> List[SubtitleItem]:
        """
        合并连续的相同字幕 - 精确时间轴版本
        参考 video-subtitle-extractor 的实现
        使用 Levenshtein 距离判断文本相似度
        """
        if not subtitles:
            return subtitles
        
        # 按帧索引排序（而不是时间）
        subtitles.sort(key=lambda x: x.frame_index)
        
        merged_subtitles = []
        i = 0
        
        while i < len(subtitles):
            current = subtitles[i]
            start_time = current.start_time
            start_frame = current.frame_index
            
            # 查找连续相同的字幕
            j = i
            similar_group = [current]  # 记录相似的字幕组
            
            while j < len(subtitles) - 1:
                next_subtitle = subtitles[j + 1]
                
                # 使用文本相似度判断（去除空格后比较）
                current_text = current.text.replace(' ', '').strip()
                next_text = next_subtitle.text.replace(' ', '').strip()
                
                # 计算相似度（简单版本：完全相同或编辑距离很小）
                similarity = self._calculate_text_similarity(current_text, next_text)
                
                # 如果相似度低于阈值，找到了结束点
                if similarity < 0.8:  # 80%相似度阈值
                    break
                
                # 相似，继续
                similar_group.append(next_subtitle)
                j += 1
            
            # 计算结束时间
            if j < len(subtitles):
                # 使用最后一个相似字幕的时间作为结束
                end_time = subtitles[j].start_time
                end_frame = subtitles[j].frame_index
            else:
                # 最后一组字幕，使用最后一帧的时间+1秒
                end_time = subtitles[j].start_time + 1.0
                end_frame = subtitles[j].frame_index
            
            # 从相似组中选择最长的文本（最完整的识别结果）
            best_text = max(similar_group, key=lambda x: len(x.text.replace(' ', ''))).text
            best_confidence = max(similar_group, key=lambda x: x.confidence).confidence
            
            # 创建合并后的字幕
            merged_subtitle = SubtitleItem(
                start_time=start_time,
                end_time=end_time,
                text=best_text,
                confidence=best_confidence,
                frame_index=start_frame
            )
            merged_subtitles.append(merged_subtitle)
            
            # 移动到下一组
            i = j + 1
        
        return merged_subtitles
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度
        使用简化的 Levenshtein 距离算法
        返回 0-1 之间的相似度值
        """
        if text1 == text2:
            return 1.0
        
        if not text1 or not text2:
            return 0.0
        
        # 使用 difflib 计算相似度（Python 标准库）
        from difflib import SequenceMatcher
        return SequenceMatcher(None, text1, text2).ratio()
    
    def export_srt(self, subtitles: List[SubtitleItem], output_path: str) -> bool:
        """导出SRT字幕文件"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for i, subtitle in enumerate(subtitles, 1):
                    if subtitle.is_watermark:
                        continue
                        
                    start_time = self._seconds_to_srt_time(subtitle.start_time)
                    end_time = self._seconds_to_srt_time(subtitle.end_time)
                    
                    f.write(f"{i}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{subtitle.text}\n\n")
            
            return True
        except Exception as e:
            print(f"导出SRT文件失败: {e}")
            return False
    
    def export_txt(self, subtitles: List[SubtitleItem], output_path: str) -> bool:
        """导出纯文本字幕文件"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for subtitle in subtitles:
                    if not subtitle.is_watermark:
                        f.write(f"{subtitle.text}\n")
            
            return True
        except Exception as e:
            print(f"导出TXT文件失败: {e}")
            return False
    
    def _seconds_to_srt_time(self, seconds: float) -> str:
        """将秒数转换为SRT时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def get_system_resource_info(self) -> SystemResourceInfo:
        """获取系统资源信息"""
        try:
            import psutil
            
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            memory_usage = memory.percent
            
            # 检查GPU
            gpu_available = False
            gpu_memory_usage = None
            
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu_available = True
                    gpu_memory_usage = gpus[0].memoryUtil * 100
            except ImportError:
                # GPUtil 不可用，尝试其他方法检测GPU
                try:
                    import torch
                    if torch.cuda.is_available():
                        gpu_available = True
                except ImportError:
                    pass
            except Exception:
                pass
            
            # 磁盘空间
            try:
                disk = psutil.disk_usage('.')
                disk_space = disk.free / (1024**3)  # GB
            except:
                disk_space = 0
            
            return SystemResourceInfo(
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                gpu_available=gpu_available,
                gpu_memory_usage=gpu_memory_usage,
                disk_space=disk_space
            )
        except Exception as e:
            print(f"获取系统资源信息失败: {e}")
            return SystemResourceInfo(
                cpu_usage=0,
                memory_usage=0,
                gpu_available=False,
                disk_space=0
            )
    
    def get_supported_languages(self) -> Dict[str, str]:
        """获取支持的语言列表"""
        return self.supported_languages.copy()