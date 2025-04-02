import aiohttp
import asyncio
import logging
import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
import threading
import requests
from wcferry import Wcf
from cache_manager import cache_manager

logger = logging.getLogger(__name__)

class MoyuCalendar:
    """摸鱼日历服务"""
    
    # 单例实例
    _instance = None
    
    def __new__(cls, config: dict = None):
        """实现单例模式"""
        if cls._instance is None:
            cls._instance = super(MoyuCalendar, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: dict):
        """
        初始化摸鱼日历服务
        
        Args:
            config: 配置字典
        """
        # 如果已经初始化过，则直接返回
        if getattr(self, '_initialized', False):
            logger.debug("摸鱼日历服务已经初始化，跳过重复初始化")
            return
            
        self.config = config.get('moyu_calendar', {})
        self.enabled = self.config.get('enabled', False)
        
        # 获取播报群聊列表
        self.enabled_rooms = set(self.config.get('enabled_rooms', []))
        
        # 获取播报时间
        broadcast_time = self.config.get('broadcast_time', "08:00")
        hour, minute = map(int, broadcast_time.split(':'))
        self.broadcast_hour = hour
        self.broadcast_minute = minute
        
        # 最大推迟播报时间（分钟）
        self.max_delay_minutes = self.config.get('max_delay_minutes', 60)
        
        # 摸鱼日历API
        self.moyu_api = "https://api.dudunas.top/api/moyu"
        
        # 节假日API
        self.holiday_api = "https://timor.tech/api/holiday/info"
        
        # 获取当前脚本所在目录
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        # 缓存根目录
        self.cache_root = os.path.join(self.current_dir, 'cache')
        # 摸鱼日历缓存目录
        self.cache_dir = os.path.join(self.cache_root, 'moyu')
        # 图片缓存目录
        self.image_cache_dir = os.path.join(self.cache_dir, 'images')
        # 播报历史记录文件路径
        self.broadcast_history_file = os.path.join(self.cache_dir, 'broadcast_history.json')
        
        # 创建所需的目录
        os.makedirs(self.cache_root, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.image_cache_dir, exist_ok=True)
        
        # 播报历史记录，避免重复播报
        self.broadcast_history = cache_manager.load_broadcast_history('moyu')
        
        # 缓存今日摸鱼日历图片路径
        self.cached_image_path = None
        self.cached_image_url = None
        self.image_download_time = None
        
        # 缓存过期天数，默认7天
        self.cache_expiry_days = self.config.get('cache_expiry_days', 7)
        
        # wcf实例，用于发送消息
        self.wcf = None
        
        # 清理旧缓存图片
        self._cleanup_old_cache_files()
        
        # 检查缓存目录中是否已存在今日图片
        self._check_existing_image()
        
        logger.info(f"摸鱼日历服务初始化完成，启用状态: {'已启用' if self.enabled else '已禁用'}")
        if self.enabled:
            logger.info(f"播报时间: {self.broadcast_hour:02d}:{self.broadcast_minute:02d}")
            logger.info(f"最大推迟时间: {self.max_delay_minutes}分钟")
            logger.info(f"已配置群聊: {len(self.enabled_rooms)}个")
            logger.info(f"缓存图片保留天数: {self.cache_expiry_days}天")
            logger.info(f"缓存目录: {self.cache_dir}")
            
        # 标记为已初始化
        self._initialized = True
    
    def _load_broadcast_history(self) -> Dict[str, float]:
        """从文件加载播报历史记录"""
        try:
            if os.path.exists(self.broadcast_history_file):
                with open(self.broadcast_history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                logger.info(f"已从文件加载播报历史记录: {len(history)}条")
                return history
        except Exception as e:
            logger.error(f"加载播报历史记录失败: {e}")
        return {}

    def _save_broadcast_history(self) -> None:
        """保存播报历史记录到文件"""
        try:
            with open(self.broadcast_history_file, 'w', encoding='utf-8') as f:
                json.dump(self.broadcast_history, f)
            logger.debug("已保存播报历史记录到文件")
        except Exception as e:
            logger.error(f"保存播报历史记录失败: {e}")
    
    async def _make_request(self, url: str, params: dict = None) -> Optional[dict]:
        """发送HTTP请求并获取响应"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"请求失败: {url}, 状态码: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"请求出错: {url}, 错误: {e}")
            return None
    
    async def is_workday(self) -> bool:
        """检查今日是否为工作日"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            url = f"{self.holiday_api}/{today}"
            
            response = await self._make_request(url)
            if not response:
                # 如果API请求失败，默认按工作日处理
                logger.warning("节假日API请求失败，默认按工作日处理")
                return True
            
            # 检查返回结果
            if response.get('code') == 0:  # 请求成功
                holiday_data = response.get('type', {})
                is_holiday = holiday_data.get('type', 0) in [1, 2]  # 1:周末, 2:节假日
                is_workday = holiday_data.get('type', 0) in [0, 3]  # 0:工作日, 3:补班
                
                if is_holiday:
                    logger.info(f"今日是节假日/周末: {holiday_data.get('name', '未知')}")
                    return False
                elif is_workday:
                    logger.info(f"今日是工作日: {holiday_data.get('name', '工作日')}")
                    return True
                else:
                    logger.warning(f"未知的日期类型: {holiday_data}")
                    return True  # 默认按工作日处理
            else:
                logger.error(f"节假日API返回错误: {response.get('message', '未知错误')}")
                return True  # 默认按工作日处理
                
        except Exception as e:
            logger.error(f"检查工作日状态出错: {e}")
            return True  # 出错时默认按工作日处理
    
    async def get_moyu_calendar(self) -> Optional[Dict]:
        """获取摸鱼日历信息"""
        try:
            response = await self._make_request(self.moyu_api)
            if not response:
                logger.error("获取摸鱼日历失败")
                return None
            
            if response.get('code') == 200:
                return response.get('data', {})
            else:
                logger.error(f"摸鱼日历API返回错误: {response}")
                return None
                
        except Exception as e:
            logger.error(f"获取摸鱼日历出错: {e}")
            return None
    
    def _get_broadcast_key(self) -> str:
        """获取当日播报标识"""
        return datetime.now().strftime('%Y-%m-%d')
    
    def _is_already_broadcasted(self) -> bool:
        """检查今日是否已经播报过"""
        key = self._get_broadcast_key()
        return key in self.broadcast_history
    
    def _is_image_cached_today(self) -> bool:
        """检查图片是否在今天已经缓存"""
        if not self.image_download_time:
            return False
            
        try:
            # 如果 image_download_time 已经是 datetime 对象，直接使用
            if isinstance(self.image_download_time, datetime):
                cache_day = self.image_download_time.strftime('%Y-%m-%d')
            else:
                # 如果是时间戳，转换为 datetime
                cache_day = datetime.fromtimestamp(self.image_download_time).strftime('%Y-%m-%d')
                
            current_day = datetime.now().strftime('%Y-%m-%d')
            return cache_day == current_day
        except Exception as e:
            logger.error(f"检查图片缓存时间出错: {e}")
            return False
    
    def _is_cache_file_valid(self) -> bool:
        """检查缓存文件是否存在且有效"""
        if not self._is_image_cached_today():
            return False
        return os.path.exists(self.cached_image_path) and os.path.getsize(self.cached_image_path) > 0
    
    def _mark_as_broadcasted(self) -> None:
        """标记今日已播报"""
        key = self._get_broadcast_key()
        self.broadcast_history[key] = datetime.now().timestamp()
        
        # 保存到文件
        self._save_broadcast_history()
        
        # 清理过期的历史记录
        self._clear_old_broadcast_history()
    
    def _clear_old_broadcast_history(self) -> None:
        """清理过期的播报历史记录"""
        current_time = time.time()
        keys_to_delete = []
        
        for key, timestamp in self.broadcast_history.items():
            # 超过3天的记录删除
            if current_time - timestamp > 3 * 24 * 60 * 60:
                keys_to_delete.append(key)
        
        if keys_to_delete:
            for key in keys_to_delete:
                del self.broadcast_history[key]
            # 保存更新后的历史记录
            self._save_broadcast_history()
            logger.info(f"已清理{len(keys_to_delete)}条过期播报记录")
    
    def _cleanup_old_cache_files(self) -> None:
        """清理旧的缓存图片文件"""
        cache_manager.cleanup_old_files('moyu', self.cache_expiry_days)
    
    async def download_moyu_calendar_image(self) -> Tuple[bool, str, str]:
        """下载摸鱼日历图片，返回 (是否成功, 图片路径, 图片URL)"""
        # 先清理旧缓存文件
        self._cleanup_old_cache_files()
        
        # 如果今天已经下载过，直接返回缓存
        if self._is_cache_file_valid():
            logger.info(f"使用已缓存的摸鱼日历图片: {self.cached_image_path}")
            return True, self.cached_image_path, self.cached_image_url
            
        try:
            # 获取摸鱼日历
            moyu_data = await self.get_moyu_calendar()
            if not moyu_data:
                logger.error("获取摸鱼日历信息失败")
                return False, "", ""
            
            # 获取图片URL和标题
            image_url = moyu_data.get('url')
            title = moyu_data.get('title', '摸鱼人日历')
            
            logger.info(f"获取到摸鱼日历: {title}, 图片URL: {image_url}")
            
            if not image_url:
                logger.error("摸鱼日历图片URL为空")
                return False, "", ""
            
            # 设置图片保存路径
            image_dir = cache_manager.get_image_cache_dir('moyu')
            if not image_dir:
                return False, "", ""
                
            image_file = os.path.join(image_dir, f"moyu_{datetime.now().strftime('%Y%m%d')}.jpg")
            logger.info(f"图片将保存到: {image_file}")
            
            # 添加重试机制
            retry_count = 3
            retry_delays = [5, 10, 20]  # 递增的延迟时间（秒）
            
            for attempt in range(retry_count):
                try:
                    logger.info(f"尝试下载图片，第{attempt+1}次尝试...")
                    
                    # 使用同步请求下载图片，设置不同的连接超时和读取超时
                    response = requests.get(
                        image_url, 
                        timeout=(5, 30),  # 连接超时5秒，读取超时30秒
                        stream=True       # 使用流式下载
                    )
                    
                    if response.status_code == 200:
                        # 流式下载图片，分块写入
                        with open(image_file, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):  # 8KB块
                                if chunk:  # 过滤掉保持连接活跃的空块
                                    f.write(chunk)
                        
                        logger.info(f"图片已保存到: {image_file}, 大小: {os.path.getsize(image_file)} 字节")
                        
                        # 检查文件是否存在
                        if not os.path.exists(image_file):
                            logger.error(f"图片文件不存在: {image_file}")
                            if attempt < retry_count - 1:
                                logger.info(f"将在{retry_delays[attempt]}秒后重试...")
                                await asyncio.sleep(retry_delays[attempt])
                                continue
                            return False, "", image_url
                        
                        # 更新缓存信息
                        self.cached_image_path = image_file
                        self.cached_image_url = image_url
                        self.image_download_time = time.time()
                        
                        return True, image_file, image_url
                    else:
                        logger.error(f"下载图片失败，HTTP状态码: {response.status_code}")
                        if attempt < retry_count - 1:
                            logger.info(f"将在{retry_delays[attempt]}秒后重试...")
                            await asyncio.sleep(retry_delays[attempt])
                            continue
                
                except requests.exceptions.Timeout as e:
                    # 专门处理超时异常
                    logger.error(f"下载图片超时: {e}")
                    if attempt < retry_count - 1:
                        logger.info(f"将在{retry_delays[attempt]}秒后重试...")
                        await asyncio.sleep(retry_delays[attempt])
                        continue
                    
                except Exception as e:
                    # 处理其他异常
                    logger.error(f"下载摸鱼日历图片出错: {e}", exc_info=True)
                    if attempt < retry_count - 1:
                        logger.info(f"将在{retry_delays[attempt]}秒后重试...")
                        await asyncio.sleep(retry_delays[attempt])
                        continue
            
            # 所有重试都失败
            logger.error(f"在{retry_count}次尝试后仍无法下载图片")
            return False, "", image_url
                
        except Exception as e:
            logger.error(f"下载摸鱼日历图片出错: {e}", exc_info=True)
            # 保留已获取的image_url，即使异常也返回URL
            return False, "", image_url
    
    async def broadcast_moyu_calendar(self, room_ids: List[str]) -> None:
        """广播摸鱼日历到指定群聊"""
        try:
            if not self.wcf:
                logger.error("WCF实例未设置，无法发送消息")
                return
            
            # 确保图片已下载
            success, image_file, image_url = await self.download_moyu_calendar_image()
            
            # 发送消息到每个群
            for room_id in room_ids:
                try:
                    # 发送文本消息
                    self.wcf.send_text(f"【摸鱼日历】今天是{datetime.now().strftime('%Y年%m月%d日')}，工作日要注意摸鱼哦~", room_id)
                    logger.info(f"文本消息已发送到群 {room_id}")
                    
                    # 如果成功下载了图片，发送图片
                    if success and os.path.exists(image_file):
                        # 发送图片
                        logger.info(f"正在向群 {room_id} 发送图片: {image_file}")
                        self.wcf.send_image(image_file, room_id)
                        logger.info(f"图片已发送到群 {room_id}")
                    else:
                        # 发送图片链接作为备用
                        if image_url:
                            self.wcf.send_text(f"摸鱼日历图片获取失败，请查看: {image_url}", room_id)
                        else:
                            self.wcf.send_text("摸鱼日历图片获取失败", room_id)
                except Exception as e:
                    logger.error(f"向群 {room_id} 发送消息失败: {e}", exc_info=True)
            
            # 标记已播报
            self._mark_as_broadcasted()
                
        except Exception as e:
            logger.error(f"播报摸鱼日历出错: {e}", exc_info=True)
    
    async def check_workday_and_prefetch(self) -> bool:
        """检查今日是否是工作日，如果是，提前下载图片"""
        try:
            # 首先检查缓存图片是否已存在且有效
            if self._is_cache_file_valid():
                logger.info("今日摸鱼日历图片已缓存，无需预下载")
                return True
                
            # 检查是否工作日
            is_work_day = await self.is_workday()
            
            if is_work_day:
                logger.info("今日是工作日，开始提前下载摸鱼日历图片")
                success, _, _ = await self.download_moyu_calendar_image()
                if success:
                    logger.info("摸鱼日历图片已提前下载完成，等待播报时间")
                return True
            else:
                logger.info("今日不是工作日，不需要下载摸鱼日历图片")
                return False
                
        except Exception as e:
            logger.error(f"检查工作日并预下载图片出错: {e}", exc_info=True)
            return False
    
    async def check_and_broadcast(self, room_ids: List[str] = None) -> None:
        """检查并播报摸鱼日历"""
        try:
            # 如果功能未启用，直接返回
            if not self.enabled:
                return
            
            # 如果没有指定群聊，使用配置中的群聊
            if not room_ids:
                room_ids = list(self.enabled_rooms)
            
            # 如果没有可播报的群聊，直接返回
            if not room_ids:
                return
            
            # 检查是否已经播报过
            if self._is_already_broadcasted():
                return
            
            # 检查当前时间
            now = datetime.now()
            
            # 首先检查缓存图片是否存在且有效
            cache_valid = self._is_cache_file_valid()
            
            # 计算当前时间距离目标播报时间的分钟数
            target_time = now.replace(hour=self.broadcast_hour, minute=self.broadcast_minute, second=0, microsecond=0)
            time_diff_minutes = (target_time - now).total_seconds() / 60
            
            # 如果当前时间在7点之后，且还没到播报时间或在最大推迟时间内
            if (now.hour >= 7 and time_diff_minutes > -self.max_delay_minutes and 
                (time_diff_minutes > 0 or not cache_valid)):  # 如果还没到播报时间或没有有效缓存
                
                # 每10分钟尝试一次
                if now.minute % 10 == 0:
                    # 如果图片已经缓存成功且文件有效，则跳过预下载
                    if cache_valid:
                        logger.info("图片已成功缓存，跳过本次预下载尝试")
                        return
                    
                    # 检查今日是否工作日
                    is_work_day = await self.is_workday()
                    if not is_work_day:
                        logger.info("今日不是工作日，跳过本次预下载尝试")
                        return
                    
                    logger.info(f"尝试在{now.hour:02d}:{now.minute:02d}预下载摸鱼日历图片")
                    success, _, _ = await self.download_moyu_calendar_image()
                    if success:
                        logger.info("预下载摸鱼日历图片成功，准备进行播报")
                    else:
                        # 计算距离播报时间还有多久
                        if time_diff_minutes > 0:
                            logger.info(f"预下载摸鱼日历图片失败，将在10分钟后重试（距离播报时间还有{int(time_diff_minutes)}分钟）")
                        else:
                            delay_minutes = min(-time_diff_minutes, self.max_delay_minutes)
                            logger.info(f"预下载摸鱼日历图片失败，已推迟播报{int(delay_minutes)}分钟，将在10分钟后重试")
                    return
            
            # 检查是否到了播报时间（考虑推迟时间）
            is_broadcast_time = (
                now.hour == self.broadcast_hour and 
                now.minute >= self.broadcast_minute and 
                now.minute < self.broadcast_minute + 5
            )
            is_delayed_time = (
                time_diff_minutes <= 0 and 
                -time_diff_minutes <= self.max_delay_minutes and 
                now.minute % 10 == 0
            )
            
            if not (is_broadcast_time or is_delayed_time):
                return
            
            # 如果到了播报时间但还没有图片，继续尝试下载
            if not cache_valid:
                # 检查今日是否工作日
                is_work_day = await self.is_workday()
                if not is_work_day:
                    logger.info("今日不是工作日，不播报摸鱼日历")
                    # 标记已检查，避免重复检查
                    self._mark_as_broadcasted()
                    return
                
                # 尝试最后一次下载
                logger.info("播报时间已到，进行最后一次下载尝试")
                success, _, _ = await self.download_moyu_calendar_image()
                if not success and -time_diff_minutes < self.max_delay_minutes:
                    logger.info(f"下载失败，推迟到下一个10分钟整点继续尝试（最多推迟{self.max_delay_minutes}分钟）")
                    return
            
            # 播报摸鱼日历
            logger.info("开始播报摸鱼日历")
            await self.broadcast_moyu_calendar(room_ids)
            
        except Exception as e:
            logger.error(f"检查并播报摸鱼日历出错: {e}")
    
    async def start_moyu_calendar_service(self) -> None:
        """启动摸鱼日历服务"""
        if not self.enabled:
            logger.info("摸鱼日历服务未启用")
            return
        
        logger.info("摸鱼日历服务已启动")
        
        # 服务启动时，先检查缓存是否已存在
        if self._is_cache_file_valid():
            logger.info("检测到已缓存的今日摸鱼日历图片，无需重新下载")
        else:
            # 缓存不存在或无效，检查今日是否工作日并提前下载图片
            logger.info("未检测到有效的缓存图片，将检查今日是否工作日并尝试下载")
            await self.check_workday_and_prefetch()
        
        while True:
            try:
                # 检查并播报摸鱼日历
                await self.check_and_broadcast()
                
                # 每分钟检查一次
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"摸鱼日历服务运行出错: {e}")
                await asyncio.sleep(60)  # 出错后暂停1分钟
    
    def _check_existing_image(self) -> None:
        """检查缓存目录中是否已存在今日图片"""
        try:
            # 获取图片缓存目录
            image_dir = cache_manager.get_image_cache_dir('moyu')
            if not image_dir:
                return
                
            # 获取今日日期
            today = datetime.now().strftime('%Y%m%d')
            image_file = os.path.join(image_dir, f"moyu_{today}.jpg")
            
            # 检查文件是否存在
            if os.path.exists(image_file):
                self.cached_image_path = image_file
                self.image_download_time = datetime.fromtimestamp(os.path.getmtime(image_file))
                logger.info(f"发现今日摸鱼日历图片缓存: {image_file}")
        except Exception as e:
            logger.error(f"检查缓存图片时出错: {e}")

    def _download_image(self, url: str) -> Optional[str]:
        """下载图片并保存到缓存目录"""
        try:
            # 确保缓存目录存在
            cache_dir = cache_manager.get_image_cache_dir('moyu')
            os.makedirs(cache_dir, exist_ok=True)
            
            # 生成文件名
            filename = f"moyu_{datetime.now().strftime('%Y%m%d')}.jpg"
            filepath = os.path.join(cache_dir, filename)
            
            # 下载图片
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # 保存图片
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            # 更新下载时间（存储为时间戳）
            self.image_download_time = int(datetime.now().timestamp())
            
            logger.info(f"图片已保存到: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"下载图片失败: {e}")
            return None 