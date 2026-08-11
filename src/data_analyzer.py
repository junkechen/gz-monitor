# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 数据分析模块
提供统计分析、趋势分析、对比分析等功能
"""

import statistics
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import numpy as np


class DataAnalyzer:
    """数据分析器"""

    def __init__(self):
        self.history_data = {}
        self.realtime_data = {}

    def calculate_statistics(self, values: List[float]) -> Dict:
        """
        计算基础统计信息
        返回: {mean, median, std, min, max, q1, q3, iqr}
        """
        if not values or len(values) == 0:
            return {}

        # 过滤None值
        vals = [v for v in values if v is not None]
        if not vals:
            return {}

        sorted_vals = sorted(vals)
        n = len(vals)

        stats = {
            'count': n,
            'mean': round(statistics.mean(vals), 2),
            'median': round(statistics.median(vals), 2),
            'std': round(statistics.stdev(vals) if n > 1 else 0, 2),
            'min': round(min(vals), 2),
            'max': round(max(vals), 2),
            'range': round(max(vals) - min(vals), 2),
        }

        # 四分位数
        if n >= 4:
            q1_idx = n // 4
            q3_idx = 3 * n // 4
            stats['q1'] = round(sorted_vals[q1_idx], 2)
            stats['q3'] = round(sorted_vals[q3_idx], 2)
            stats['iqr'] = round(stats['q3'] - stats['q1'], 2)

        # 变异系数
        if stats['mean'] != 0:
            stats['cv'] = round((stats['std'] / abs(stats['mean'])) * 100, 2)

        return stats

    def analyze_trend(self, times: List[str], values: List[float], window: int = 5) -> Dict:
        """
        分析数据趋势
        window: 移动平均窗口大小
        返回: {trend, slope, r_squared, moving_avg, change_rate}
        """
        if len(values) < 2:
            return {'trend': '数据不足', 'slope': 0, 'r_squared': 0, 'moving_avg': [], 'change_rate': 0}

        # 过滤None值
        valid_data = [(t, v) for t, v in zip(times, values) if v is not None]
        if len(valid_data) < 2:
            return {'trend': '数据不足', 'slope': 0, 'r_squared': 0, 'moving_avg': [], 'change_rate': 0}

        valid_times = [t for t, v in valid_data]
        valid_values = [v for t, v in valid_data]

        # 计算移动平均
        moving_avg = []
        for i in range(len(valid_values)):
            start = max(0, i - window + 1)
            window_vals = valid_values[start:i+1]
            moving_avg.append(round(statistics.mean(window_vals), 2))

        # 线性回归分析趋势
        try:
            x = np.arange(len(valid_values))
            y = np.array(valid_values)

            # 线性回归
            coeffs = np.polyfit(x, y, 1)
            slope = round(coeffs[0], 4)
            intercept = round(coeffs[1], 2)

            # 计算R平方
            y_pred = np.polyval(coeffs, x)
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = round(1 - (ss_res / ss_tot) if ss_tot != 0 else 0, 4)

            # 判断趋势
            if r_squared < 0.3:
                trend = "波动较大，无明显趋势"
            elif slope > 0.01:
                trend = "上升趋势 ⬆️"
            elif slope < -0.01:
                trend = "下降趋势 ⬇️"
            else:
                trend = "稳定趋势 ➡️"

            # 变化率
            if len(valid_values) >= 2:
                change_rate = round(((valid_values[-1] - valid_values[0]) / valid_values[0]) * 100, 2)
            else:
                change_rate = 0

            return {
                'trend': trend,
                'slope': slope,
                'r_squared': r_squared,
                'moving_avg': moving_avg,
                'change_rate': change_rate,
                'intercept': intercept
            }
        except Exception as e:
            return {
                'trend': f"分析失败: {str(e)}",
                'slope': 0,
                'r_squared': 0,
                'moving_avg': moving_avg,
                'change_rate': 0
            }

    def compare_periods(self, data_period1: List[float], data_period2: List[float]) -> Dict:
        """
        对比两个时期的数据
        返回: {period1_stats, period2_stats, diff, percent_change}
        """
        stats1 = self.calculate_statistics(data_period1)
        stats2 = self.calculate_statistics(data_period2)

        if not stats1 or not stats2:
            return {}

        mean_diff = round(stats2['mean'] - stats1['mean'], 2)
        if stats1['mean'] != 0:
            percent_change = round((mean_diff / abs(stats1['mean'])) * 100, 2)
        else:
            percent_change = 0

        return {
            'period1_stats': stats1,
            'period2_stats': stats2,
            'diff': mean_diff,
            'percent_change': percent_change,
            'interpretation': self._interpret_change(percent_change)
        }

    def _interpret_change(self, percent_change: float) -> str:
        """解释变化"""
        if abs(percent_change) < 5:
            return "基本稳定"
        elif percent_change > 20:
            return "显著增加 ⬆️"
        elif percent_change > 5:
            return "轻微增加 ↗️"
        elif percent_change < -20:
            return "显著减少 ⬇️"
        else:
            return "轻微减少 ↘️"

    def detect_anomalies(self, values: List[float], threshold: float = 2.0) -> List[Tuple[int, float]]:
        """
        检测异常值（基于Z-score）
        threshold: Z-score阈值，默认2.0
        返回: [(index, value), ...]
        """
        if len(values) < 4:
            return []

        # 过滤None值
        valid_indices = [i for i, v in enumerate(values) if v is not None]
        valid_values = [v for v in values if v is not None]

        if len(valid_values) < 4:
            return []

        try:
            mean = statistics.mean(valid_values)
            std = statistics.stdev(valid_values) if len(valid_values) > 1 else 0

            if std == 0:
                return []

            anomalies = []
            for idx, value in zip(valid_indices, valid_values):
                z_score = (value - mean) / std
                if abs(z_score) > threshold:
                    anomalies.append((idx, value, round(z_score, 2)))

            return anomalies
        except Exception:
            return []

    def calculate_compliance_rate(self, values: List[float], threshold: float) -> Dict:
        """
        计算达标率
        返回: {compliance_rate, exceed_count, total_count}
        """
        if not values:
            return {'compliance_rate': 0, 'exceed_count': 0, 'total_count': 0}

        valid_values = [v for v in values if v is not None]
        if not valid_values:
            return {'compliance_rate': 0, 'exceed_count': 0, 'total_count': 0}

        exceed_count = sum(1 for v in valid_values if v > threshold)
        total_count = len(valid_values)
        compliance_rate = round(((total_count - exceed_count) / total_count) * 100, 2)

        return {
            'compliance_rate': compliance_rate,
            'exceed_count': exceed_count,
            'total_count': total_count
        }

    def generate_summary_report(self, data_dict: Dict[str, List[float]], thresholds: Dict[str, float]) -> Dict:
        """
        生成汇总分析报告
        data_dict: {参数名: [数值列表]}
        thresholds: {参数名: 阈值}
        """
        report = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'parameters': []
        }

        for param_name, values in data_dict.items():
            threshold = thresholds.get(param_name)

            # 基础统计
            stats = self.calculate_statistics(values)

            # 达标率
            if threshold:
                compliance = self.calculate_compliance_rate(values, threshold)
            else:
                compliance = None

            # 趋势分析
            times = list(range(len(values)))
            trend = self.analyze_trend(times, values)

            # 异常检测
            anomalies = self.detect_anomalies(values)

            param_report = {
                'name': param_name,
                'statistics': stats,
                'compliance': compliance,
                'trend': trend,
                'anomalies': anomalies,
                'threshold': threshold
            }

            report['parameters'].append(param_report)

        return report


class TrendAnalyzer:
    """趋势分析器"""

    @staticmethod
    def analyze_hourly_pattern(values: List[float]) -> Dict:
        """分析小时模式（按小时聚合数据）"""
        if len(values) < 24:
            return {}

        # 模拟24小时数据
        hourly_data = []
        for hour in range(24):
            idx = hour % len(values)
            hourly_data.append(values[idx] if idx < len(values) else None)

        hourly_data = [v for v in hourly_data if v is not None]

        if not hourly_data:
            return {}

        stats = {
            'peak_hour': hourly_data.index(max(hourly_data)),
            'peak_value': max(hourly_data),
            'low_hour': hourly_data.index(min(hourly_data)),
            'low_value': min(hourly_data),
            'mean': round(statistics.mean(hourly_data), 2),
            'pattern': TrendAnalyzer._identify_pattern(hourly_data)
        }

        return stats

    @staticmethod
    def _identify_pattern(hourly_data: List[float]) -> str:
        """识别数据模式"""
        if len(hourly_data) < 12:
            return "数据不足"

        # 计算上午(6-12)和下午(12-18)的均值
        morning_mean = statistics.mean(hourly_data[6:12]) if len(hourly_data) > 12 else 0
        afternoon_mean = statistics.mean(hourly_data[12:18]) if len(hourly_data) > 18 else 0

        if morning_mean > afternoon_mean * 1.2:
            return "上午偏高"
        elif afternoon_mean > morning_mean * 1.2:
            return "下午偏高"
        else:
            return "分布均匀"


class ComparisonAnalyzer:
    """对比分析器"""

    @staticmethod
    def compare_multi_params(data_dict: Dict[str, List[float]]) -> Dict:
        """对比多个参数的数据"""
        comparison = {
            'parameters': []
        }

        for param_name, values in data_dict.items():
            if not values:
                continue

            analyzer = DataAnalyzer()
            stats = analyzer.calculate_statistics(values)

            comparison['parameters'].append({
                'name': param_name,
                'mean': stats.get('mean', 0),
                'std': stats.get('std', 0),
                'cv': stats.get('cv', 0)
            })

        # 按均值排序
        comparison['parameters'].sort(key=lambda x: x['mean'], reverse=True)

        return comparison
