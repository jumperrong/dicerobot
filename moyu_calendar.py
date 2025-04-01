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

logger = logging.getLogger(__name__)

class MoyuCalendarService:
    """摸鱼日历服务"""
    
    # 单例实例
    _instance = None
    
    def __new__(cls, config: dict = None):
        """实现单例模式"""
        if cls._instance is None:
            cls._instance = super(MoyuCalendarService, cls).__new__(cls)
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
        
        # 摸鱼日历API
        self.moyu_api = "https://api.dudunas.top/api/moyu"
        
        # 节假日API
        self.holiday_api = "https://timor.tech/api/holiday/info"
        
        # 播报历史记录，避免重复播报
        self.broadcast_history = {}
        
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
        
        # 检查temp目录中是否已存在今日图片
        self._check_existing_image()
        
        logger.info(f"摸鱼日历服务初始化完成，启用状态: {'已启用' if self.enabled else '已禁用'}")
        if self.enabled:
            logger.info(f"播报时间: {self.broadcast_hour:02d}:{self.broadcast_minute:02d}")
            logger.info(f"已配置群聊: {len(self.enabled_rooms)}个")
            logger.info(f"缓存图片保留天数: {self.cache_expiry_days}天")
            
        # 标记为已初始化
        self._initialized = True
    
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
        """检查今日图片是否已缓存"""
        # 如果没有缓存路径或下载时间，则未缓存
        if not self.cached_image_path or not self.image_download_time:
            return False
            
        # 检查缓存时间是否是今天
        today = datetime.now().strftime('%Y-%m-%d')
        cache_day = datetime.fromtimestamp(self.image_download_time).strftime('%Y-%m-%d')
        return today == cache_day
    
    def _is_cache_file_valid(self) -> bool:
        """检查缓存文件是否存在且有效"""
        if not self._is_image_cached_today():
            return False
        return os.path.exists(self.cached_image_path) and os.path.getsize(self.cached_image_path) > 0
    
    def _mark_as_broadcasted(self) -> None:
        """标记今日已播报"""
        key = self._get_broadcast_key()
        self.broadcast_history[key] = datetime.now().timestamp()
        
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
        
        for key in keys_to_delete:
            del self.broadcast_history[key]
    
    def _cleanup_old_cache_files(self) -> None:
        """清理旧的缓存图片文件"""
        try:
            # 获取当前脚本所在目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 临时目录路径
            temp_dir = os.path.join(current_dir, 'temp')
            
            # 如果临时目录不存在，返回
            if not os.path.exists(temp_dir):
                return
                
            # 获取当前时间
            now = datetime.now()
            # 计算过期时间点
            expiry_date = now - timedelta(days=self.cache_expiry_days)
            
            # 遍历临时目录中的所有文件
            removed_count = 0
            for filename in os.listdir(temp_dir):
                # 只处理摸鱼日历图片文件
                if not filename.startswith('moyu_') or not filename.endswith('.jpg'):
                    continue
                    
                # 获取文件的完整路径
                file_path = os.path.join(temp_dir, filename)
                
                try:
                    # 尝试从文件名中提取日期（格式：moyu_YYYYMMDD.jpg）
                    date_str = filename[5:13]  # 提取YYYYMMDD部分
                    file_date = datetime.strptime(date_str, '%Y%m%d')
                    
                    # 检查文件是否过期
                    if file_date < expiry_date:
                        # 删除过期文件
                        os.remove(file_path)
                        removed_count += 1
                        logger.debug(f"已删除过期缓存图片: {filename}")
                except (ValueError, IndexError):
                    # 如果文件名格式不正确，跳过
                    logger.warning(f"无法解析缓存文件日期: {filename}")
                    continue
                except Exception as e:
                    # 其他错误，记录但不中断清理过程
                    logger.error(f"删除缓存文件时出错: {filename}, 错误: {e}")
                    continue
                    
            if removed_count > 0:
                logger.info(f"已清理 {removed_count} 个过期缓存图片文件 (超过 {self.cache_expiry_days} 天)")
        except Exception as e:
            logger.error(f"清理缓存文件出错: {e}", exc_info=True)
    
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
            
            # 获取当前脚本所在目录的绝对路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 创建临时目录
            temp_dir = os.path.join(current_dir, 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            
            # 设置图片保存路径
            image_file = os.path.join(temp_dir, f"moyu_{datetime.now().strftime('%Y%m%d')}.jpg")
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
            
            # 预下载时间点：2点、4点、6点，在前5分钟内尝试下载
            prefetch_hours = [2, 4, 6]
            if now.hour in prefetch_hours and now.minute in range(0, 5):
                # 如果图片已经缓存成功且文件有效，则跳过预下载
                if cache_valid:
                    logger.info(f"图片已成功缓存，跳过{now.hour}点的预下载尝试")
                    return
                
                # 检查今日是否工作日
                is_work_day = await self.is_workday()
                if not is_work_day:
                    logger.info(f"今日不是工作日，跳过{now.hour}点的预下载尝试")
                    return
                
                logger.info(f"尝试在{now.hour}点预下载摸鱼日历图片")
                success, _, _ = await self.download_moyu_calendar_image()
                if success:
                    logger.info(f"{now.hour}点预下载摸鱼日历图片成功，今日将不再尝试预下载")
                else:
                    logger.info(f"{now.hour}点预下载摸鱼日历图片失败，将在下个时间点再次尝试")
                return
            
            # 检查当前时间是否到了播报时间
            if now.hour != self.broadcast_hour or now.minute not in range(self.broadcast_minute, self.broadcast_minute + 5):
                return
            
            # 提前检查图片是否已经下载
            if not cache_valid:
                # 检查今日是否工作日
                is_work_day = await self.is_workday()
                if not is_work_day:
                    logger.info("今日不是工作日，不播报摸鱼日历")
                    # 标记已检查，避免重复检查
                    self._mark_as_broadcasted()
                    return
                    
                # 如果是工作日但还没有下载图片，立即下载
                logger.info("播报前最后检查图片，开始下载")
                await self.download_moyu_calendar_image()
            
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
        """检查temp目录中是否存在今日的摸鱼日历图片"""
        try:
            # 获取当前脚本所在目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 临时目录路径
            temp_dir = os.path.join(current_dir, 'temp')
            
            # 如果临时目录不存在，返回
            if not os.path.exists(temp_dir):
                return
                
            # 今日日期格式化
            today_str = datetime.now().strftime('%Y%m%d')
            # 预期的图片文件名
            expected_filename = f"moyu_{today_str}.jpg"
            # 完整路径
            image_path = os.path.join(temp_dir, expected_filename)
            
            # 检查文件是否存在
            if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
                logger.info(f"在启动时发现已存在的今日摸鱼日历图片: {image_path}")
                # 设置缓存图片信息
                self.cached_image_path = image_path
                self.image_download_time = time.time()  # 使用当前时间作为下载时间
                # 虽然不知道原始URL，但这不影响我们使用缓存的图片
                self.cached_image_url = f"file://{image_path}"
                logger.info("已自动加载本地摸鱼日历图片缓存")
        except Exception as e:
            logger.error(f"检查已存在图片出错: {e}", exc_info=True) 