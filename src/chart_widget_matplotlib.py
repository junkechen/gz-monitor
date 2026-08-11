# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 图表组件（Matplotlib 版本，Windows 7 兼容）
使用 matplotlib 替代 WebEngine，避免兼容性问题
"""

import os
import sys
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import Qt

# 设置 matplotlib 使用 Qt5 后端
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt


class ChartWidget(QWidget):
    """图表组件（使用 Matplotlib，Windows 7 兼容）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        # 创建 matplotlib 图形
        self.figure = Figure(figsize=(8, 4), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self._layout.addWidget(self.canvas)

    def plot_series(self, times, series_list, title="数据曲线"):
        """绘制多条曲线"""
        # 清空之前的图形
        self.figure.clear()
        
        # 创建子图
        ax = self.figure.add_subplot(111)
        
        # 绘制每条曲线
        for series in series_list:
            ax.plot(times, series['data'], 
                   marker='o', linewidth=2, 
                   label=series['name'])
        
        # 设置标题和标签
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_xlabel("时间", fontsize=10)
        ax.set_ylabel("数值", fontsize=10)
        
        # 旋转 x 轴标签
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # 添加图例
        ax.legend(loc='best', fontsize=9)
        
        # 添加网格
        ax.grid(True, alpha=0.3)
        
        # 调整布局
        self.figure.tight_layout()
        
        # 刷新画布
        self.canvas.draw()

    def clear(self):
        """清空图表"""
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.text(0.5, 0.5, '暂无数据', 
               horizontalalignment='center',
               verticalalignment='center',
               transform=ax.transAxes,
               fontsize=12, color='gray')
        ax.set_xticks([])
        ax.set_yticks([])
        self.canvas.draw()
