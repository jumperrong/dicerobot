import logging
import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Union
import json
import hashlib
import os
from cache_manager import cache_manager

logger = logging.getLogger(__name__)

class WeatherService:
    """天气服务类"""
    
    def __init__(self, config: dict):
        """初始化天气服务"""
        self.api_key = config.get('api_key')
        self.api_urls = config.get('api_urls', {})
        self.default_city = config.get('default_city', '无锡')
        self.warning_config = config.get('warning', {})
        self.daily_report = config.get('daily_report', {})
        self.wcf = None  # WeChatFerry 实例，后续设置
        self.warning_cache = {}  # 预警信息缓存
        self.location_cache = {}  # 地理位置缓存
        self.last_warning_check = None  # 上次检查预警的时间
        self.enabled_rooms = set()  # 已启用的群聊列表
        self._cache_modified = False  # 缓存是否被修改
        self._last_save_time = None  # 上次保存时间
        self._save_interval = 300  # 保存间隔（秒），改为5分钟
        
        # 从配置中获取已启用的群聊
        if 'group_chat' in config:
            enabled_rooms = config['group_chat'].get('enabled_rooms', [])
            self.enabled_rooms = set(enabled_rooms)
        
        # 解析定点播报时间
        self.broadcast_times = self._parse_broadcast_times(
            self.daily_report.get('broadcast_times', [])
        )
        
        # 加载缓存数据(同时用于播报历史和预警缓存)
        cache_data = cache_manager.load_broadcast_history('weather')
        # 设置播报历史
        self.broadcast_history = cache_data
        # 设置预警缓存
        self.warning_cache = cache_data.get('warnings', {})
        logger.debug(f"已加载预警缓存: {len(self.warning_cache)} 条记录")
        
        # 验证配置
        if not self.api_key:
            logger.error("未配置天气API密钥")
        if not self.api_urls:
            logger.error("未配置天气API地址")
        
        # 添加重试配置
        self.retry_count = config.get('retry', {}).get('count', 3)
        self.retry_delay = config.get('retry', {}).get('delay', 1)
        
        logger.info(f"天气服务初始化完成:")
        logger.info(f"- 默认城市: {self.default_city}")
        logger.info(f"- 播报时间: {', '.join(f'{h:02d}:{m:02d}' for h, m in self.broadcast_times)}")
        logger.info(f"- 预警功能: {'已启用' if self.warning_config.get('enabled') else '未启用'}")
        if self.enabled_rooms:
            logger.info(f"- 已启用群聊: {len(self.enabled_rooms)}个")
            for room in self.enabled_rooms:
                logger.info(f"  • {room}")
        else:
            logger.info("- 已启用群聊: 无")
    
    def _parse_broadcast_times(self, times: List[Union[str, int]]) -> List[tuple[int, int]]:
        """解析定点播报时间"""
        broadcast_times = []
        for time in times:
            try:
                if isinstance(time, int):
                    # 整点
                    broadcast_times.append((time, 0))
                elif isinstance(time, str):
                    # 精确时间
                    hour, minute = map(int, time.split(':'))
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        broadcast_times.append((hour, minute))
                    else:
                        logger.error(f"无效的播报时间: {time}")
                else:
                    logger.error(f"不支持的时间格式: {time}")
            except Exception as e:
                logger.error(f"解析播报时间出错: {time} - {e}")
        
        return sorted(broadcast_times)  # 按时间排序
    
    async def _make_request(self, url: str, params: dict) -> Optional[dict]:
        """发送API请求，支持重试机制"""
        last_error = None
        
        for attempt in range(self.retry_count):
            try:
                async with aiohttp.ClientSession() as session:
                    params['key'] = self.api_key
                    async with session.get(url, params=params, timeout=10) as response:
                        if response.status == 200:
                            return await response.json()
                        
                        # 记录非200状态码
                        logger.warning(f"API请求返回非200状态码: {response.status} (尝试 {attempt + 1}/{self.retry_count})")
                        last_error = f"HTTP {response.status}"
                        
            except asyncio.TimeoutError:
                logger.warning(f"API请求超时 (尝试 {attempt + 1}/{self.retry_count})")
                last_error = "请求超时"
            except Exception as e:
                logger.warning(f"API请求出错: {e} (尝试 {attempt + 1}/{self.retry_count})")
                last_error = str(e)
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < self.retry_count - 1:
                retry_delay = self.retry_delay * (attempt + 1)  # 递增延迟
                logger.info(f"等待 {retry_delay} 秒后重试...")
                await asyncio.sleep(retry_delay)
        
        # 所有重试都失败
        logger.error(f"API请求在 {self.retry_count} 次尝试后仍然失败: {last_error}")
        return None
    
    async def get_location(self, city: str) -> Optional[dict]:
        """获取城市地理信息"""
        # 检查缓存
        if city in self.location_cache:
            return self.location_cache[city]
        
        try:
            url = self.api_urls.get('geo')
            if not url:
                logger.error("未配置地理位置API地址")
                return None
            
            params = {'location': city}
            response = await self._make_request(url, params)
            
            if response and response.get('code') == '200':
                location = response.get('location', [{}])[0]
                if location:
                    # 缓存结果
                    self.location_cache[city] = location
                    
                    # 标记缓存已修改
                    self._cache_modified = True
                    # 尝试保存缓存
                    self._save_warning_cache()
                    
                    return location
            
            logger.error(f"获取地理位置失败: {response}")
            return None
            
        except Exception as e:
            logger.error(f"获取地理位置时出错: {e}")
            return None
    
    async def get_weather(self, days: str = 'now', city: str = None) -> str:
        """获取天气信息"""
        try:
            city = city or self.default_city
            location = await self.get_location(city)
            
            if not location:
                return f"未找到城市: {city}"
            
            # 根据days参数选择API
            if days == 'now':
                url = self.api_urls.get('weather')
            elif days in ['3', '7']:
                url = self.api_urls.get(f'weather_{days}d')
            else:
                return "天气预报只支持查询3天或7天"
            
            if not url:
                logger.error(f"未配置天气API地址: weather_{days}d")
                return "天气服务配置错误"
            
            params = {'location': location['id']}
            response = await self._make_request(url, params)
            
            if not response or response.get('code') != '200':
                return "获取天气信息失败"
            
            # 格式化天气信息
            if days == 'now':
                return self._format_current_weather(response['now'])
            else:
                return self._format_forecast_weather(response['daily'], int(days))
                
        except Exception as e:
            logger.error(f"获取天气信息时出错: {e}")
            return "获取天气信息失败"
    
    def _format_current_weather(self, weather: dict) -> str:
        """格式化实时天气信息"""
        return (
            f"实时天气:\n"
            f"温度: {weather['temp']}°C\n"
            f"体感温度: {weather['feelsLike']}°C\n"
            f"天气: {weather['text']}\n"
            f"风向: {weather['windDir']}\n"
            f"风力等级: {weather['windScale']}级\n"
            f"相对湿度: {weather['humidity']}%"
        )
    
    def _format_forecast_weather(self, daily: List[dict], days: int) -> str:
        """格式化天气预报信息"""
        forecast = []
        for day in daily[:days]:
            date = datetime.strptime(day['fxDate'], '%Y-%m-%d').strftime('%m月%d日')
            forecast.append(
                f"{date}:\n"
                f"天气: {day['textDay']}/{day['textNight']}\n"
                f"温度: {day['tempMin']}°C ~ {day['tempMax']}°C\n"
                f"风向: {day['windDirDay']}\n"
                f"风力: {day['windScaleDay']}级"
            )
        return "\n\n".join(forecast)
    
    async def get_indices(self, city: str = None) -> str:
        """获取天气指数信息"""
        try:
            city = city or self.default_city
            location = await self.get_location(city)
            
            if not location:
                return f"未找到城市: {city}"
            
            url = self.api_urls.get('indices')
            if not url:
                logger.error("未配置天气指数API地址")
                return "天气指数服务配置错误"
            
            params = {
                'location': location['id'],
                'type': '1,2,3,5,9'  # 运动,洗车,穿衣,空气污染扩散条件,感冒
            }
            
            response = await self._make_request(url, params)
            
            if not response or response.get('code') != '200':
                return "获取天气指数失败"
            
            return self._format_indices(response['daily'])
            
        except Exception as e:
            logger.error(f"获取天气指数时出错: {e}")
            return "获取天气指数失败"
    
    def _format_indices(self, indices: List[dict]) -> str:
        """格式化天气指数信息"""
        formatted = ["生活指数:"]
        for index in indices:
            # 添加指数名称、等级和详细说明
            formatted.extend([
                f"{index['name']}: {index['category']}",
                f"• {index['text']}"  # 添加详细说明
            ])
        return "\n".join(formatted)
    
    async def get_warning(self, city: str = None) -> Optional[str]:
        """获取天气预警信息"""
        try:
            city = city or self.default_city
            location = await self.get_location(city)
            
            if not location:
                logger.warning(f"获取预警信息失败: 未找到城市 {city} 的地理信息")
                return None
            
            url = self.api_urls.get('warning')
            if not url:
                logger.error("未配置天气预警API地址")
                return None
            
            params = {'location': location['id']}
            logger.debug(f"正在请求预警信息: {url} (城市: {city}, ID: {location['id']})")
            
            response = await self._make_request(url, params)
            
            if not response:
                logger.error(f"获取预警信息失败: API请求失败")
                return None
                
            if response.get('code') != '200':
                logger.error(f"获取预警信息失败: API返回错误 - {response.get('code')}")
                return None
            
            warnings = response.get('warning', [])
            if not warnings:
                logger.debug(f"当前无预警信息 (城市: {city})")
                return None
            
            logger.debug(f"成功获取预警信息: {city} - {len(warnings)}条预警")
            return self._format_warning_info(warnings)
            
        except Exception as e:
            logger.error(f"获取天气预警时出错: {e}", exc_info=True)
            return None
    
    def _format_warning_info(self, warnings: List[dict]) -> str:
        """格式化天气预警信息"""
        formatted = ["天气预警:"]
        for warning in warnings:
            pub_time = datetime.strptime(
                warning['pubTime'], 
                '%Y-%m-%dT%H:%M%z'
            ).strftime('%Y-%m-%d %H:%M')
            
            formatted.extend([
                f"发布时间: {pub_time}",
                f"预警标题: {warning['title']}",
                f"预警详情: {warning['text']}"
            ])
            
            # 添加开始时间和结束时间（如果有）
            if 'startTime' in warning:
                start_time = datetime.strptime(
                    warning['startTime'],
                    '%Y-%m-%dT%H:%M%z'
                ).strftime('%Y-%m-%d %H:%M')
                formatted.append(f"开始时间: {start_time}")
                
            if 'endTime' in warning:
                end_time = datetime.strptime(
                    warning['endTime'],
                    '%Y-%m-%dT%H:%M%z'
                ).strftime('%Y-%m-%d %H:%M')
                formatted.append(f"结束时间: {end_time}")
                
        return "\n".join(formatted)
    
    def _get_broadcast_key(self) -> str:
        """获取当前日期作为播报记录的键"""
        return datetime.now().strftime('%Y-%m-%d')
    
    def _clear_old_broadcast_history(self) -> None:
        """清理过期的播报记录"""
        current_date = self._get_broadcast_key()
        old_dates = [date for date in self.broadcast_history if date != current_date]
        for date in old_dates:
            del self.broadcast_history[date]
        
        # 标记缓存已修改
        self._cache_modified = True
        # 尝试保存缓存
        self._save_warning_cache()
    
    def _is_already_broadcasted(self, hour: int, minute: int) -> bool:
        """检查指定时间是否已经播报过"""
        current_date = self._get_broadcast_key()
        if current_date not in self.broadcast_history:
            self.broadcast_history[current_date] = set()
        return f"{hour:02d}:{minute:02d}" in self.broadcast_history[current_date]
    
    def _mark_as_broadcasted(self, hour: int, minute: int) -> None:
        """标记指定时间已播报"""
        current_date = self._get_broadcast_key()
        if current_date not in self.broadcast_history:
            self.broadcast_history[current_date] = set()
        self.broadcast_history[current_date].add(f"{hour:02d}:{minute:02d}")
        
        # 标记缓存已修改
        self._cache_modified = True
        # 尝试保存缓存
        self._save_warning_cache()
    
    async def check_and_broadcast(self, room_ids: List[str] = None) -> None:
        """检查并广播天气信息"""
        if not self.wcf or not room_ids:
            return
            
        try:
            # 清理过期的播报记录
            self._clear_old_broadcast_history()
            
            # 检查是否在播报时间
            current_time = datetime.now()
            current_hour = current_time.hour
            current_minute = current_time.minute
            
            # 检查是否到达任一播报时间
            should_broadcast = False
            broadcast_hour = None
            broadcast_minute = None
            
            for hour, minute in self.broadcast_times:
                if (current_hour, current_minute) == (hour, minute):
                    if not self._is_already_broadcasted(hour, minute):
                        should_broadcast = True
                        broadcast_hour = hour
                        broadcast_minute = minute
                        break
            
            if not should_broadcast:
                return
                
            # 获取天气信息
            weather_info = await self.get_weather()
            indices_info = await self.get_indices()
            warning_info = await self.get_warning()
            
            # 组合信息
            broadcast_msg = f"{self.default_city}天气播报:\n\n{weather_info}\n\n{indices_info}"
            if warning_info:
                broadcast_msg += f"\n\n{warning_info}"
            
            # 发送到所有启用的群聊
            for room_id in room_ids:
                self.wcf.send_text(broadcast_msg, room_id)
                logger.info(f"已发送天气播报到群 {room_id}")
            
            # 标记该时间点已播报
            self._mark_as_broadcasted(broadcast_hour, broadcast_minute)
            logger.info(f"已完成 {broadcast_hour:02d}:{broadcast_minute:02d} 的天气播报")
                
        except Exception as e:
            logger.error(f"天气播报出错: {e}")
    
    def _parse_time(self, time_str: str) -> datetime:
        """解析时间字符串，支持多种格式"""
        try:
            # 尝试解析带时区的ISO格式 "2023-04-04T10:30+08:00"
            return datetime.strptime(time_str, '%Y-%m-%dT%H:%M%z')
        except ValueError:
            try:
                # 尝试解析普通格式 "2024-12-18 16:27"
                return datetime.strptime(time_str, '%Y-%m-%d %H:%M')
            except ValueError as e:
                logger.error(f"无法解析时间格式: {time_str}")
                raise e

    async def start_weather_report(self, report_func) -> None:
        """启动天气播报"""
        try:
            # 等待wcf实例和群聊列表设置完成
            retry_count = 0
            max_retries = 5
            while (not self.wcf or not self.enabled_rooms) and retry_count < max_retries:
                retry_count += 1
                logger.info(f"等待WCF实例和群聊列表初始化... ({retry_count}/{max_retries})")
                await asyncio.sleep(1)
            
            if not self.wcf:
                logger.error("WCF实例未设置，无法启动天气播报服务")
                return
            
            if not self.enabled_rooms:
                logger.warning("未配置启用的群聊，天气消息将无法发送")
            
            # 如果预警功能已启用，立即执行初始预警检查
            if self.warning_config.get('enabled'):
                logger.info("正在进行初始预警信息检查...")
                warning_info = await self.get_warning()
                if warning_info:
                    logger.info("发现预警信息:")
                    warnings = self._parse_warnings(warning_info)
                    new_warnings = 0
                    
                    for warning in warnings:
                        if not self._validate_warning(warning):
                            logger.error(f"预警信息不完整: {warning}")
                            continue
                            
                        warning_id = self._generate_warning_id(warning)
                        logger.info(f"- {warning.get('title', '未知预警')} ({warning.get('pubTime', '未知时间')})")
                        
                        # 检查预警是否已过期
                        current_time = datetime.now()
                        if 'endTime' in warning:
                            # 使用预警的结束时间
                            end_time = self._parse_time(warning['endTime'])
                            if current_time > end_time:
                                logger.info(f"  • 预警已过期，跳过")
                                continue
                        elif 'startTime' in warning:
                            # 使用开始时间+24小时
                            start_time = self._parse_time(warning['startTime'])
                            if current_time > start_time + timedelta(hours=24):
                                logger.info(f"  • 预警已过期，跳过")
                                continue
                        else:
                            # 使用发布时间+24小时
                            pub_time = self._parse_time(warning['pubTime'])
                            if current_time > pub_time + timedelta(hours=24):
                                logger.info(f"  • 预警已过期，跳过")
                                continue
                        
                        # 检查是否已经发送过该预警
                        if self._is_warning_sent(warning_id):
                            logger.info(f"  • 已发送过此预警，跳过")
                            continue
                        
                        # 如果有启用的群聊，立即发送预警
                        if self.enabled_rooms:
                            # 缓存并发送预警
                            self._cache_warning(warning_id, warning)
                            await self._broadcast_warning(warning, list(self.enabled_rooms))
                            new_warnings += 1
                        else:
                            logger.warning("无启用的群聊，预警消息将无法发送")
                    
                    if new_warnings > 0:
                        logger.info(f"已发送 {new_warnings} 条新预警")
                    else:
                        logger.info("没有需要发送的新预警")
                else:
                    logger.info("当前无预警信息")
                
                # 更新最后检查时间，避免立即再次检查
                self.last_warning_check = datetime.now()
            
            # 启动定时任务循环
            logger.info("天气播报服务启动完成，开始定时任务")
            while True:
                try:
                    # 执行定时播报
                    await report_func()
                    
                    # 检查天气预警（只在距离上次检查超过间隔时间后执行）
                    if self.warning_config.get('enabled'):
                        current_time = datetime.now()
                        if not self.last_warning_check or \
                           (current_time - self.last_warning_check).total_seconds() >= \
                           self.warning_config.get('interval', 10) * 60:
                            await self.check_weather_warnings(list(self.enabled_rooms))
                    
                    # 每分钟检查一次
                    await asyncio.sleep(60)
                except Exception as e:
                    logger.error(f"天气播报循环出错: {e}")
                    await asyncio.sleep(60)  # 出错后等待一分钟再试
                    
        except Exception as e:
            logger.error(f"启动天气播报服务失败: {e}", exc_info=True)
    
    def _should_send_warning(self, warning_id: str, warning: dict) -> bool:
        """判断是否应该发送预警"""
        try:
            # 获取24小时前的时间点
            time_window = datetime.now() - timedelta(hours=24)
            
            # 检查所有缓存的预警
            for cache_key, cached_warning in self.warning_cache.items():
                if warning_id in cache_key:  # 找到匹配的预警ID
                    # 检查发送时间是否在24小时内
                    send_time = datetime.strptime(cached_warning['time'], '%Y-%m-%d %H:%M:%S')
                    if send_time > time_window:
                        # 已在24小时内发送
                        return False
            
            # 检查预警是否已过期
            current_time = datetime.now()
            if 'endTime' in warning:
                # 使用预警的结束时间
                end_time = self._parse_time(warning['endTime'])
                if current_time > end_time:
                    return False
            elif 'startTime' in warning:
                # 使用开始时间+24小时
                start_time = self._parse_time(warning['startTime'])
                if current_time > start_time + timedelta(hours=24):
                    return False
            else:
                # 使用发布时间+24小时
                pub_time = self._parse_time(warning['pubTime'])
                if current_time > pub_time + timedelta(hours=24):
                    return False
            
            # 未在24小时内发送过且未过期
            return True
            
        except Exception as e:
            logger.error(f"检查预警发送状态出错: {e}")
            return False  # 出错不发送预警
    
    async def check_weather_warnings(self, room_ids: List[str] = None) -> None:
        """检查天气预警并送通知"""
        if not self.wcf or not room_ids:
            return
            
        try:
            # 检查是否启用了预警功能
            if not self.warning_config.get('enabled'):
                return
            
            # 检查时间间隔
            current_time = datetime.now()
            if self.last_warning_check:
                interval_minutes = self.warning_config.get('interval', 10)  # 默认10分钟
                elapsed = (current_time - self.last_warning_check).total_seconds() / 60
                if elapsed < interval_minutes:
                    return
            
            # 更新最后检查时间
            self.last_warning_check = current_time
            
            # 获取预警信息
            warning_info = await self.get_warning()
            if not warning_info:
                logger.debug("预警检查完成: 无预警信息")
                return
            
            # 解析预警信息并处理每个预警
            warnings = self._parse_warnings(warning_info)
            if warnings:
                logger.info(f"发现 {len(warnings)} 条预警信息:")
                for warning in warnings:
                    logger.info(f"- {warning.get('title', '未知预警')} ({warning.get('pub_time', '未知时间')})")
            
            new_warnings = 0
            for warning in warnings:
                # 验证预警信息完整性
                if not self._validate_warning(warning):
                    logger.error(f"预警信息不完整: {warning}")
                    continue
                
                # 生成预警ID
                warning_id = self._generate_warning_id(warning)
                
                # 检查是否应该发送预警
                if self._should_send_warning(warning_id, warning):
                    # 缓存并发送预警
                    self._cache_warning(warning_id, warning)
                    await self._broadcast_warning(warning, room_ids)
                    new_warnings += 1
                else:
                    logger.debug(f"跳过预警: {warning.get('title')} (已发送或已过期)")
            
            # 清理过期缓存
            self._clear_old_warning_cache()
            
            logger.info(f"预警检查完成: {new_warnings} 条新预警发送")
            
        except Exception as e:
            logger.error(f"检查天气预警时出错: {e}", exc_info=True)
    
    def _parse_warnings(self, warning_info: str) -> List[dict]:
        """解析预警信息"""
        warnings = []
        current_warning = {}
        
        for line in warning_info.split('\n'):
            if line.startswith('发布时间:'):
                if current_warning:
                    warnings.append(current_warning)
                current_warning = {'pub_time': line.split(':', 1)[1].strip()}
            elif line.startswith('预警标题:'):
                current_warning['title'] = line.split(':', 1)[1].strip()
            elif line.startswith('预警详情:'):
                current_warning['text'] = line.split(':', 1)[1].strip()
            elif line.startswith('开始时间:'):
                current_warning['start_time'] = line.split(':', 1)[1].strip()
            elif line.startswith('结束时间:'):
                current_warning['end_time'] = line.split(':', 1)[1].strip()
        
        if current_warning:
            warnings.append(current_warning)
        
        # 转换API格式到内部格式
        converted_warnings = []
        for warning in warnings:
            converted = {
                'pubTime': warning.get('pub_time'),
                'title': warning.get('title'),
                'text': warning.get('text')
            }
            if 'start_time' in warning:
                converted['startTime'] = warning['start_time']
            if 'end_time' in warning:
                converted['endTime'] = warning['end_time']
            converted_warnings.append(converted)
            
        return converted_warnings
    
    def _validate_warning(self, warning: dict) -> bool:
        """验证预警信息的完整性"""
        required_fields = ['pubTime', 'title', 'text']
        return all(field in warning and warning[field] for field in required_fields)
    
    def _generate_warning_id(self, warning: dict) -> str:
        """生成预警ID"""
        warning_key = f"{warning['title']}_{warning['pubTime']}"
        return hashlib.md5(warning_key.encode()).hexdigest()
    
    def _is_warning_sent(self, warning_id: str) -> bool:
        """检查预警是否在24小时内已发送且未过期"""
        # 获取24小时前的时间点
        time_window = datetime.now() - timedelta(hours=24)
        
        # 检查所有缓存的预警
        for cache_key, warning_info in self.warning_cache.items():
            if warning_id in cache_key:  # 找到匹配的预警ID
                try:
                    # 检查发送时间是否在24小时内
                    send_time = datetime.strptime(warning_info['time'], '%Y-%m-%d %H:%M:%S')
                    if send_time > time_window:
                        # 检查是否过期
                        if 'expire_time' in warning_info:
                            expire_time = datetime.strptime(warning_info['expire_time'], '%Y-%m-%d %H:%M:%S')
                            if datetime.now() > expire_time:
                                # 预警已过期，从缓存中删除
                                del self.warning_cache[cache_key]
                                self._cache_modified = True
                                self._save_warning_cache()
                                return False
                        return True  # 24小时内发送过且未过期
                except Exception as e:
                    logger.error(f"检查预警发送时间出错: {e}")
        
        return False  # 24小时内未发送过
    
    def _cache_warning(self, warning_id: str, warning: dict) -> None:
        """缓存预警信息"""
        current_time = datetime.now()
        cache_key = f"{current_time.strftime('%Y%m%d%H%M%S')}_{warning_id}"
        
        # 计算过期时间
        try:
            if 'endTime' in warning:
                # 如果有结束时间，直接使用
                expire_time = self._parse_time(warning['endTime'])
            elif 'startTime' in warning:
                # 如果有开始时间，设置为24小时后
                start_time = self._parse_time(warning['startTime'])
                expire_time = start_time + timedelta(hours=24)
            else:
                # 如果都没有，使用发布时间后24小时
                pub_time = self._parse_time(warning['pubTime'])
                expire_time = pub_time + timedelta(hours=24)
        except Exception as e:
            logger.error(f"解析预警时间出错: {e}, 使用默认24小时过期")
            expire_time = current_time + timedelta(hours=24)

        self.warning_cache[cache_key] = {
            'time': current_time.strftime('%Y-%m-%d %H:%M:%S'),
            'title': warning['title'],
            'pubTime': warning['pubTime'],
            'expire_time': expire_time.strftime('%Y-%m-%d %H:%M:%S')
        }
        # 标记缓存已修改
        self._cache_modified = True
        # 尝试保存缓存
        self._save_warning_cache()
    
    async def _broadcast_warning(self, warning: dict, room_ids: List[str]) -> None:
        """广播预警信息"""
        warning_msg = self._format_warning_message(warning)
        
        logger.info(f"正在发送预警: {warning.get('title')} ({warning.get('pubTime')})")
        success_count = 0
        for room_id in room_ids:
            try:
                self.wcf.send_text(warning_msg, room_id)
                logger.info(f"✓ 已发送到群 {room_id}")
                success_count += 1
            except Exception as e:
                logger.error(f"× 发送到群 {room_id} 失败: {e}")
        
        logger.info(f"预警发送完成: {success_count}/{len(room_ids)} 个群发送成功")
    
    def _format_warning_message(self, warning: dict) -> str:
        """格式化预警消息"""
        # 格式化时间
        pub_time = self._parse_time(warning['pubTime']).strftime('%Y-%m-%d %H:%M')
        
        msg = [
            "⚠️ 天气预警通知 ⚠️\n",
            f"发布时间: {pub_time}",
            f"预警标题: {warning['title']}",
            f"预警详情: {warning['text']}"
        ]
        
        # 添加开始时间和结束时间（如果有）
        if 'startTime' in warning:
            start_time = self._parse_time(warning['startTime']).strftime('%Y-%m-%d %H:%M')
            msg.append(f"开始时间: {start_time}")
            
        if 'endTime' in warning:
            end_time = self._parse_time(warning['endTime']).strftime('%Y-%m-%d %H:%M')
            msg.append(f"结束时间: {end_time}")
        
        return "\n".join(msg)
    
    def _clear_old_warning_cache(self) -> None:
        """清理过期的预警缓存"""
        try:
            # 获取24小时前的时间点
            time_window = datetime.now() - timedelta(hours=24)
            
            # 找出需要删除的缓存项
            expired_keys = []
            for cache_key, warning_info in self.warning_cache.items():
                try:
                    # 检查发送时间是否超过24小时
                    send_time = datetime.strptime(warning_info['time'], '%Y-%m-%d %H:%M:%S')
                    if send_time < time_window:
                        expired_keys.append(cache_key)
                        continue
                    
                    # 检查是否过期
                    if 'expire_time' in warning_info:
                        expire_time = datetime.strptime(warning_info['expire_time'], '%Y-%m-%d %H:%M:%S')
                        if datetime.now() > expire_time:
                            expired_keys.append(cache_key)
                            
                except Exception as e:
                    logger.error(f"检查预警缓存时间出错: {e}")
                    expired_keys.append(cache_key)  # 出错的缓存项也删除
            
            # 删除过期的缓存项
            if expired_keys:
                for key in expired_keys:
                    del self.warning_cache[key]
                logger.debug(f"已清理 {len(expired_keys)} 条过期预警记录")
                # 标记缓存已修改
                self._cache_modified = True
                # 尝试保存缓存
                self._save_warning_cache()
            
        except Exception as e:
            logger.error(f"清理预警缓存时出错: {e}")
    
    def _load_warning_cache(self) -> None:
        """加载预警缓存"""
        # 此方法被保留仅为兼容性，实际加载已在__init__中完成
        pass
    
    def _save_warning_cache(self) -> None:
        """保存预警缓存"""
        try:
            current_time = datetime.now()
            
            # 如果缓存未被修改，直接返回
            if not self._cache_modified:
                return
                
            # 检查是否需要保存
            if self._last_save_time:
                elapsed = (current_time - self._last_save_time).total_seconds()
                if elapsed < self._save_interval:
                    return
            
            # 保存到缓存管理器
            cache_data = {
                'warnings': self.warning_cache
            }
            cache_manager.save_broadcast_history('weather', cache_data)
            logger.debug("保存预警缓存")
            
            # 更新状态
            self._cache_modified = False
            self._last_save_time = current_time
            
        except Exception as e:
            logger.error(f"保存预警缓存失败: {e}")

