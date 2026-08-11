# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 独立数据分析窗口（简化修复版）
只修复企业未登录问题，保持简洁
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTextEdit, QSplitter,
    QGroupBox, QFormLayout
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from src.config import COLORS
from src.enhanced_chart_widget import EnhancedChartWidget
from src.data_analyzer import DataAnalyzer
from src.ai_advisor import AIAdvisor


class DataAnalysisWindow(QMainWindow):
    """独立的数据分析窗口"""

    def __init__(self, multi_client):
        super().__init__()
        self.multi_client = multi_client
        self.data_analyzer = DataAnalyzer()
        self.ai_advisor = AIAdvisor()
        self.enhanced_chart = EnhancedChartWidget()

        self._init_ui()

    def _init_ui(self):
        """初始化界面"""
        self.setWindowTitle("GZ安环监测系统 - 数据分析与AI建议")
        self.setMinimumSize(1200, 800)

        # 中央组件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # 分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：图表区域
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(10)

        # 企业选择
        selection_group = QGroupBox("选择企业")
        selection_layout = QFormLayout()

        self.enterprise_combo = QComboBox()
        self.enterprise_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
                font-size: 13px;
            }}
        """)

        # 填充企业列表
        from src.account_manager import load_accounts
        all_accounts = load_accounts()
        
        for acc in all_accounts:
            name = acc['name']
            # 检查登录状态
            client = self.multi_client.clients.get(name)
            if client and client.logged_in:
                display_name = f"✓ {name}"
            else:
                display_name = f"✗ {name}"
            self.enterprise_combo.addItem(display_name, name)

        selection_layout.addRow("企业:", self.enterprise_combo)
        selection_group.setLayout(selection_layout)
        left_layout.addWidget(selection_group)

        # 图表类型选择
        chart_group = QGroupBox("图表类型")
        chart_layout = QFormLayout()

        self.chart_type_combo = QComboBox()
        self.chart_type_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
                font-size: 13px;
            }}
        """)
        
        chart_types = ["折线图", "柱状图", "饼图", "仪表盘", "散点图", "箱线图"]
        for chart_type in chart_types:
            self.chart_type_combo.addItem(chart_type)

        chart_layout.addRow("类型:", self.chart_type_combo)
        chart_group.setLayout(chart_layout)
        left_layout.addWidget(chart_group)

        # 按钮区域
        btn_layout = QHBoxLayout()

        refresh_btn = QPushButton("刷新数据")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        refresh_btn.clicked.connect(self._refresh_analysis)

        analyze_btn = QPushButton("深度分析")
        analyze_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        analyze_btn.clicked.connect(self._perform_deep_analysis)

        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(analyze_btn)
        left_layout.addLayout(btn_layout)

        # 图表显示区域
        chart_container = QGroupBox("数据可视化")
        chart_container_layout = QVBoxLayout()
        chart_container_layout.addWidget(self.enhanced_chart)
        chart_container.setLayout(chart_container_layout)
        left_layout.addWidget(chart_container)

        # 右侧：AI建议区域
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(10)

        # AI建议显示
        self.advisor_display = QTextEdit()
        self.advisor_display.setReadOnly(True)
        self.advisor_display.setStyleSheet("""
            QTextEdit {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 10px;
                font-size: 12px;
            }
        """)
        self.advisor_display.setHtml(
            "<h2>AI智能管控建议</h2>"
            "<p>请选择企业并点击刷新按钮获取智能建议。</p>"
        )
        right_layout.addWidget(self.advisor_display)

        # 统计信息
        stats_group = QGroupBox("统计摘要")
        stats_layout = QVBoxLayout()
        self.stats_display = QLabel("暂无统计数据")
        self.stats_display.setStyleSheet("""
            QLabel {
                padding: 10px;
                font-size: 12px;
            }
        """)
        stats_layout.addWidget(self.stats_display)
        stats_group.setLayout(stats_layout)
        right_layout.addWidget(stats_group)

        # 刷新AI建议按钮
        refresh_ai_btn = QPushButton("刷新AI建议")
        refresh_ai_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #fb8c00;
            }
        """)
        refresh_ai_btn.clicked.connect(self._refresh_ai_advice)
        right_layout.addWidget(refresh_ai_btn)

        # 添加到分割器
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

    def _refresh_analysis(self):
        """刷新数据分析"""
        # 获取当前选择的企业名称
        enterprise = self.enterprise_combo.currentData()
        chart_type = self.chart_type_combo.currentText()

        if not enterprise:
            self.stats_display.setText("请选择企业")
            return

        # 获取客户端
        client = self.multi_client.clients.get(enterprise)
        if not client:
            self.stats_display.setText(f"企业 {enterprise} 未找到客户端")
            return

        # 检查登录状态，未登录则自动重新登录
        if not client.logged_in:
            print(f"正在尝试重新登录 {enterprise}...")
            login_result = client.login()
            if login_result['success']:
                print(f"{enterprise} 重新登录成功")
            else:
                self.stats_display.setText(f"企业 {enterprise} 未登录且登录失败")
                return

        # 获取实时数据
        try:
            data = client.get_realtime_data()
            if data.get('success'):
                realtime_data = data.get('data', {}).get('realtime', [])

                # 统计分析
                stats = self.data_analyzer.calculate_statistics(realtime_data, enterprise)

                # 显示统计信息
                stats_text = f"""
                <b>企业:</b> {enterprise}<br>
                <b>参数数量:</b> {stats.get('param_count', 0)}<br>
                <b>平均值:</b> {stats.get('mean', 0):.2f}<br>
                <b>最大值:</b> {stats.get('max', 0):.2f}<br>
                <b>最小值:</b> {stats.get('min', 0):.2f}<br>
                <b>标准差:</b> {stats.get('std', 0):.2f}
                """
                self.stats_display.setText(stats_text)

                # 显示图表
                if realtime_data:
                    param_names = [d['name'] for d in realtime_data[:5]]
                    param_values = [d['value'] for d in realtime_data[:5]]

                    x_data = {name: [i for i in range(1)] for name in param_names}
                    y_data = {name: [val] for name, val in zip(param_names, param_values)}

                    if chart_type == "折线图":
                        self.enhanced_chart.create_line_chart(enterprise, x_data, y_data, "实时数据")
                    elif chart_type == "柱状图":
                        self.enhanced_chart.create_bar_chart(enterprise, x_data, y_data, "实时数据")
                    elif chart_type == "饼图":
                        self.enhanced_chart.create_pie_chart(enterprise, param_names, param_values, "实时数据分布")
                    elif chart_type == "仪表盘":
                        if param_values:
                            self.enhanced_chart.create_gauge_chart(enterprise, param_names[0], param_values[0], 0, max(param_values) * 1.2)
                    elif chart_type == "散点图":
                        self.enhanced_chart.create_scatter_chart(enterprise, {param_names[0]: list(range(len(param_values)))}, {param_names[0]: param_values}, "实时数据")
                    elif chart_type == "箱线图":
                        self.enhanced_chart.create_box_plot(enterprise, {param_names[0]: param_values})

                    # 同时刷新AI建议
                    self._refresh_ai_advice()
            else:
                self.stats_display.setText(f"数据获取失败: {data.get('message', '未知错误')}")

        except Exception as e:
            self.stats_display.setText(f"数据获取异常: {str(e)}")

    def _perform_deep_analysis(self):
        """执行深度分析"""
        enterprise = self.enterprise_combo.currentData()

        if not enterprise:
            self.stats_display.setText("请选择企业")
            return

        client = self.multi_client.clients.get(enterprise)
        if not client:
            self.stats_display.setText(f"企业 {enterprise} 未找到客户端")
            return

        # 检查登录状态，未登录则自动重新登录
        if not client.logged_in:
            print(f"正在尝试重新登录 {enterprise}...")
            login_result = client.login()
            if login_result['success']:
                print(f"{enterprise} 重新登录成功")
            else:
                self.stats_display.setText(f"企业 {enterprise} 未登录且登录失败")
                return

        try:
            data = client.get_realtime_data()
            if data.get('success'):
                realtime_data = data.get('data', {}).get('realtime', [])

                # 执行异常检测
                anomalies = self.data_analyzer.detect_anomalies(realtime_data, enterprise)

                # 执行趋势分析
                trends = self.data_analyzer.analyze_trends(realtime_data)

                # 显示结果
                result_text = f"<b>{enterprise} - 深度分析报告</b><br><br>"

                if anomalies:
                    result_text += "<b>检测到的异常:</b><br>"
                    for anomaly in anomalies[:3]:
                        result_text += f"- {anomaly}<br>"
                else:
                    result_text += "未检测到明显异常<br>"

                if trends:
                    result_text += "<br><b>趋势分析:</b><br>"
                    for trend in trends[:3]:
                        result_text += f"- {trend}<br>"
                else:
                    result_text += "暂无足够数据进行趋势分析<br>"

                self.stats_display.setText(result_text)
            else:
                self.stats_display.setText(f"数据获取失败: {data.get('message', '未知错误')}")

        except Exception as e:
            self.stats_display.setText(f"深度分析异常: {str(e)}")

    def _refresh_ai_advice(self):
        """刷新AI管控建议"""
        all_data = {}
        for name, client in self.multi_client.clients.items():
            if client.logged_in:
                try:
                    data = client.get_realtime_data()
                    if data.get('success'):
                        realtime = data.get('data', {}).get('realtime', [])
                        all_data[name] = realtime
                except Exception as e:
                    print(f"获取{name}数据失败: {e}")

        # 生成AI建议
        if all_data:
            advice = self.ai_advisor.generate_comprehensive_advice(all_data)

            # 格式化显示
            display_text = "<h2>AI智能管控建议报告</h2>"

            for item in advice:
                if item['type'] == 'alert':
                    priority_colors = {
                        'high': '#FF4444',
                        'medium': '#FF8800',
                        'low': '#FFBB33'
                    }
                    color = priority_colors.get(item['priority'], '#FF4444')

                    display_text += f'<h3 style="color: {color};">{item["priority"].upper()} 级别警告</h3>'
                    display_text += f"<p><b>企业:</b> {item['enterprise']}</p>"
                    display_text += f"<p><b>参数:</b> {item['param']}</p>"
                    display_text += f"<p><b>原因:</b> {item['reason']}</p>"
                    display_text += f"<p><b>建议:</b> {item['suggestion']}</p>"
                    display_text += "<hr>"

            self.advisor_display.setHtml(display_text)
        else:
            self.advisor_display.setHtml("<h2>AI智能管控建议</h2><p>暂无可用数据，请先登录并获取数据。</p>")
