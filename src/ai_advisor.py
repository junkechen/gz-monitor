# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - AI管控建议模块
基于数据分析结果生成智能化管控建议
"""

from datetime import datetime
from typing import List, Dict, Optional
from data_analyzer import DataAnalyzer, TrendAnalyzer


class AIAdvisor:
    """AI管控建议生成器"""

    def __init__(self):
        self.analyzer = DataAnalyzer()
        self.trend_analyzer = TrendAnalyzer()
        self.warning_rules = self._load_warning_rules()
        self.control_suggestions = self._load_control_suggestions()

    def _load_warning_rules(self) -> Dict:
        """加载预警规则"""
        return {
            '二氧化硫': {
                'normal': 100,
                'warning': 110,
                'danger': 120,
                'unit': 'mg/m³'
            },
            '氮氧化物': {
                'normal': 200,
                'warning': 220,
                'danger': 240,
                'unit': 'mg/m³'
            },
            '颗粒物': {
                'normal': 30,
                'warning': 33,
                'danger': 36,
                'unit': 'mg/m³'
            },
            '非甲烷总烃': {
                'normal': 50,
                'warning': 55,
                'danger': 60,
                'unit': 'mg/m³'
            },
            '化学需氧量': {
                'normal': 200,
                'warning': 220,
                'danger': 240,
                'unit': 'mg/L'
            },
            '氨氮': {
                'normal': 15,
                'warning': 16.5,
                'danger': 18,
                'unit': 'mg/L'
            },
            'pH值': {
                'normal': 9.0,
                'warning': 9.5,
                'danger': 10.0,
                'unit': ''
            }
        }

    def _load_control_suggestions(self) -> Dict:
        """加载管控建议库"""
        return {
            '废气处理': {
                '二氧化硫': {
                    'exceed': "建议：开启脱硫设备增加运行负荷，检查脱硫剂库存和投加量，优化燃烧工况以减少SO2生成",
                    'trend_up': "建议：SO2呈现上升趋势，建议提前增加脱硫剂用量，检查脱硫塔运行状态，确保处理效率",
                    'trend_down': "提示：SO2趋势下降，当前脱硫效果良好，建议维持现有工况并定期检查设备",
                    'maintenance': "建议：定期清理脱硫塔积灰，检查喷淋系统，更换老化管道和阀门"
                },
                '氮氧化物': {
                    'exceed': "建议：优化燃烧配风，降低炉膛温度，检查脱硝系统运行状态，增加还原剂投加量",
                    'trend_up': "建议：NOx有上升趋势，建议检查SCR/SNCR系统，优化空气预热器效率，监控氨逃逸",
                    'trend_down': "提示：NOx控制良好，建议继续优化燃烧控制，定期校准在线监测仪表",
                    'maintenance': "建议：定期清理催化还原剂积灰，检查喷氨格栅，校准CEMS系统"
                },
                '颗粒物': {
                    'exceed': "建议：启动备用除尘设备，检查布袋/电除尘器运行状态，增加清灰频率",
                    'trend_up': "建议：颗粒物浓度上升，建议检查滤袋破损情况，优化清灰程序，确保除尘效率",
                    'trend_down': "提示：除尘效果良好，建议维持现有工况，定期检查滤袋完整性",
                    'maintenance': "建议：定期更换损坏滤袋，检查气密性，清理灰斗积灰"
                }
            },
            '废水处理': {
                '化学需氧量': {
                    'exceed': "建议：增加曝气量，提高溶解氧浓度，延长生化池停留时间，投加碳源或营养盐",
                    'trend_up': "建议：COD有上升趋势，建议检查生化池活性，调整回流比，监测进水水质变化",
                    'trend_down': "提示：COD控制良好，建议维持现有工艺参数，定期监测污泥活性",
                    'maintenance': "建议：定期清理曝气头，检测污泥浓度，校准在线仪表"
                },
                '氨氮': {
                    'exceed': "建议：调整pH值至适宜范围（7.5-8.5），增加反硝化时间，投加碳源促进硝化反硝化",
                    'trend_up': "建议：氨氮上升趋势明显，建议检查硝化菌群活性，调整曝气策略，增加内回流比",
                    'trend_down': "提示：氨氮处理效果良好，建议继续维持DO控制，定期监测污泥指标",
                    'maintenance': "建议：定期检测硝化细菌活性，清理曝气系统，校准氨氮分析仪"
                },
                'pH值': {
                    'exceed': "建议：投加酸/碱调节pH值，检查中和池投药系统，确保pH控制在6-9范围内",
                    'trend_up': "建议：pH值偏离标准，建议检查进水pH变化，调整中和剂投加量",
                    'trend_down': "提示：pH值控制稳定，建议维持现有投药策略，定期校准pH计",
                    'maintenance': "建议：定期校准pH电极，清洗投药管路，检查中和池搅拌效果"
                }
            }
        }

    def generate_advice(self, param_name: str, current_value: float, history_values: List[float]) -> Dict:
        """
        生成管控建议
        param_name: 参数名称
        current_value: 当前值
        history_values: 历史值列表
        """
        if not history_values or len(history_values) < 2:
            return self._get_default_advice(param_name)

        # 获取参数规则
        rules = self.warning_rules.get(param_name)
        if not rules:
            return self._get_default_advice(param_name)

        # 判断排放类型
        if param_name in ['二氧化硫', '氮氧化物', '颗粒物', '非甲烷总烃']:
            treatment_type = '废气处理'
        elif param_name in ['化学需氧量', '氨氮', 'pH值']:
            treatment_type = '废水处理'
        else:
            return self._get_default_advice(param_name)

        # 分析数据
        trend = self.analyzer.analyze_trend(list(range(len(history_values))), history_values)
        stats = self.analyzer.calculate_statistics(history_values)
        anomalies = self.analyzer.detect_anomalies(history_values)

        # 生成建议
        advice = {
            'param_name': param_name,
            'current_value': round(current_value, 2),
            'unit': rules.get('unit', ''),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': self._get_status(current_value, rules),
            'trend': trend.get('trend', '未知'),
            'priority': self._calculate_priority(current_value, trend, rules, stats),
            'suggestions': []
        }

        # 根据不同情况添加建议
        suggestions = self.control_suggestions.get(treatment_type, {}).get(param_name, {})

        # 1. 超标建议
        if current_value > rules.get('warning', 0):
            advice['suggestions'].append({
                'type': '超标预警',
                'level': '高' if current_value > rules.get('danger', 0) else '中',
                'content': suggestions.get('exceed', f"{param_name}超过预警标准，建议立即采取控制措施")
            })

        # 2. 趋势建议
        if trend.get('slope', 0) > 0.05:  # 上升趋势
            advice['suggestions'].append({
                'type': '趋势预警',
                'level': '中',
                'content': suggestions.get('trend_up', f"{param_name}呈现上升趋势，建议提前干预")
            })
        elif trend.get('slope', 0) < -0.05:  # 下降趋势
            advice['suggestions'].append({
                'type': '趋势提示',
                'level': '低',
                'content': suggestions.get('trend_down', f"{param_name}呈下降趋势，继续保持")
            })

        # 3. 异常值建议
        if anomalies and len(anomalies) > 0:
            advice['suggestions'].append({
                'type': '异常提醒',
                'level': '中',
                'content': f"检测到{len(anomalies)}个异常数据点，建议检查设备运行状态和数据采集系统"
            })

        # 4. 维护建议（基于数据稳定性）
        if stats.get('cv', 0) > 30:  # 变异系数大于30%
            advice['suggestions'].append({
                'type': '维护建议',
                'level': '低',
                'content': suggestions.get('maintenance', f"{param_name}数据波动较大，建议进行设备维护")
            })

        # 5. 如果没有特殊建议，添加常规建议
        if not advice['suggestions']:
            advice['suggestions'].append({
                'type': '常规建议',
                'level': '低',
                'content': f"{param_name}运行正常，建议维持现有工况并定期巡检"
            })

        return advice

    def _get_status(self, value: float, rules: Dict) -> str:
        """获取当前状态"""
        if value > rules.get('danger', float('inf')):
            return '红色预警'
        elif value > rules.get('warning', float('inf')):
            return '橙色预警'
        elif value > rules.get('normal', float('inf')):
            return '黄色预警'
        else:
            return '正常'

    def _calculate_priority(self, current_value: float, trend: Dict, rules: Dict, stats: Dict) -> int:
        """计算建议优先级（1-5，5最高）"""
        priority = 1

        # 超标优先级最高
        if current_value > rules.get('danger', float('inf')):
            priority = 5
        elif current_value > rules.get('warning', float('inf')):
            priority = 4

        # 趋势影响优先级
        if trend.get('slope', 0) > 0.1 and priority < 4:
            priority = min(priority + 2, 5)
        elif trend.get('slope', 0) > 0.05 and priority < 3:
            priority += 1

        # 数据稳定性影响优先级
        if stats.get('cv', 0) > 40 and priority < 3:
            priority += 1

        return priority

    def _get_default_advice(self, param_name: str) -> Dict:
        """获取默认建议"""
        return {
            'param_name': param_name,
            'current_value': 0,
            'unit': '',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': '数据不足',
            'trend': '未知',
            'priority': 0,
            'suggestions': [{
                'type': '提示',
                'level': '低',
                'content': f"{param_name}暂无足够的历史数据，建议持续监测"
            }]
        }

    def generate_batch_advice(self, data_dict: Dict[str, Dict]) -> List[Dict]:
        """
        批量生成建议
        data_dict: {参数名: {'current': 值, 'history': [历史值]}}
        """
        advice_list = []

        for param_name, data in data_dict.items():
            current_value = data.get('current')
            history_values = data.get('history', [])

            if current_value is None or not history_values:
                continue

            advice = self.generate_advice(param_name, current_value, history_values)
            advice_list.append(advice)

        # 按优先级排序
        advice_list.sort(key=lambda x: x['priority'], reverse=True)

        return advice_list

    def generate_overview_report(self, advice_list: List[Dict]) -> Dict:
        """生成管控概览报告"""
        if not advice_list:
            return {
                'total': 0,
                'normal': 0,
                'warning': 0,
                'danger': 0,
                'top_priority': [],
                'summary': '暂无数据'
            }

        total = len(advice_list)
        normal_count = sum(1 for a in advice_list if a['status'] == '正常')
        warning_count = sum(1 for a in advice_list if '预警' in a['status'])
        danger_count = sum(1 for a in advice_list if '红色' in a['status'] or '橙色' in a['status'])

        top_priority = [a for a in advice_list if a['priority'] >= 4][:3]

        # 生成总结
        if danger_count > 0:
            summary = f"⚠️ 检测到{danger_count}项参数存在严重超标风险，需要立即采取管控措施！"
        elif warning_count > 0:
            summary = f"⚡ 检测到{warning_count}项参数存在超标风险，建议及时采取控制措施。"
        elif warning_count + normal_count == total:
            summary = f"✅ 所有参数运行正常，建议持续监测并定期巡检。"
        else:
            summary = f"ℹ️ 系统运行平稳，建议关注{len(top_priority)}项重点关注参数。"

        return {
            'total': total,
            'normal': normal_count,
            'warning': warning_count,
            'danger': danger_count,
            'top_priority': top_priority,
            'summary': summary,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
