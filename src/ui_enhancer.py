# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - UI增强模块
提供动画效果、渐变优化等界面美化功能
"""

from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, QTimer, pyqtProperty, QPointF
from PyQt5.QtGui import QColor
from typing import Optional, Callable


class UIEnhancer:
    """UI增强器"""

    @staticmethod
    def get_enhanced_styles(base_colors: dict) -> dict:
        """
        获取增强的样式配置
        添加动画效果、渐变优化等
        """
        enhanced = base_colors.copy()

        # 添加渐变配置
        enhanced['gradient_primary'] = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {base_colors['primary']}, stop:1 {base_colors['secondary']})"
        enhanced['gradient_reverse'] = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {base_colors['secondary']}, stop:1 {base_colors['primary']})"
        enhanced['gradient_vertical'] = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {base_colors['bg_dark']}, stop:1 {base_colors['bg_card']})"

        # 添加动画相关配置
        enhanced['animation_duration'] = 300  # 毫秒
        enhanced['easing_curve'] = "cubic-bezier(0.4, 0.0, 0.2, 1)"

        # 添加阴影配置
        enhanced['shadow_color'] = "rgba(0, 0, 0, 0.3)"
        enhanced['shadow_blur'] = 10

        return enhanced

    @staticmethod
    def get_button_style(is_primary: bool = True, is_danger: bool = False) -> str:
        """
        获取增强的按钮样式
        is_primary: 是否为主要按钮
        is_danger: 是否为危险按钮
        """
        base_colors = UIEnhancer.get_enhanced_styles({
            "primary": "#1a6b3c",
            "secondary": "#2d9e60",
            "bg_dark": "#0d1117",
            "bg_card": "#161b22",
            "text_primary": "#e6edf3",
            "warning": "#f85149"
        })

        if is_danger:
            gradient = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #d32f2f, stop:1 #b71c1c)"
            hover_gradient = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e57373, stop:1 #d32f2f)"
        elif is_primary:
            gradient = base_colors['gradient_primary']
            hover_gradient = base_colors['gradient_reverse']
        else:
            gradient = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #424242, stop:1 #616161)"
            hover_gradient = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #616161, stop:1 #757575)"

        return f"""
            QPushButton {{
                background: {gradient};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {hover_gradient};
                border: 2px solid {base_colors['accent']};
            }}
            QPushButton:pressed {{
                background: {hover_gradient};
                padding-top: 12px;
                padding-bottom: 8px;
            }}
            QPushButton:disabled {{
                background: #373e47;
                color: #8b949e;
                border: 1px solid #30363d;
            }}
        """

    @staticmethod
    def get_card_style(color: str = "primary") -> str:
        """获取卡片样式"""
        colors = {
            "primary": "#1a6b3c",
            "secondary": "#2d9e60",
            "warning": "#f85149",
            "accent": "#58a6ff",
            "success": "#3fb950"
        }

        border_color = colors.get(color, "#30363d")

        return f"""
            QGroupBox {{
                border: 2px solid {border_color};
                border-radius: 12px;
                margin-top: 10px;
                padding-top: 20px;
                font-weight: bold;
                color: #e6edf3;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #161b22, stop:1 #21262d);
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
                color: {border_color};
                font-size: 14px;
                font-weight: bold;
            }}
        """

    @staticmethod
    def get_table_style() -> str:
        """获取增强的表格样式"""
        return """
            QTableWidget {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 8px;
                gridline-color: #30363d;
                selection-background-color: #1a6b3c;
                selection-color: white;
            }
            QTableWidget::item {
                padding: 10px;
                border: none;
            }
            QTableWidget::item:hover {
                background-color: #2d9e60;
                color: white;
            }
            QTableWidget::item:selected {
                background-color: #1a6b3c;
                color: white;
            }
            QHeaderView::section {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a6b3c, stop:1 #2d9e60);
                color: white;
                padding: 12px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
            }
            QHeaderView::section:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2d9e60, stop:1 #1a6b3c);
            }
        """

    @staticmethod
    def get_label_style(size: str = "normal", color: str = "primary") -> str:
        """获取标签样式"""
        colors = {
            "primary": "#e6edf3",
            "secondary": "#8b949e",
            "accent": "#58a6ff",
            "warning": "#f85149",
            "success": "#3fb950"
        }

        sizes = {
            "small": "12px",
            "normal": "14px",
            "large": "16px",
            "xlarge": "18px"
        }

        return f"""
            QLabel {{
                color: {colors.get(color, colors['primary'])};
                font-size: {sizes.get(size, sizes['normal'])};
            }}
        """

    @staticmethod
    def get_status_badge_style(status: str) -> str:
        """获取状态标签样式"""
        colors = {
            "正常": "#3fb950",
            "黄色预警": "#ffd700",
            "橙色预警": "#ff9800",
            "红色预警": "#f85149"
        }

        bg_color = colors.get(status, "#58a6ff")

        return f"""
            QLabel {{
                background-color: {bg_color};
                color: white;
                padding: 5px 15px;
                border-radius: 15px;
                font-weight: bold;
                font-size: 12px;
            }}
        """

    @staticmethod
    def get_enhanced_window_style() -> str:
        """获取增强的窗口样式"""
        return """
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0d1117, stop:1 #161b22);
            }
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0d1117, stop:1 #161b22);
            }
        """

    @staticmethod
    def get_tab_widget_style() -> str:
        """获取增强的标签页样式"""
        return """
            QTabWidget::pane {
                border: 2px solid #1a6b3c;
                border-radius: 12px;
                background: #161b22;
            }
            QTabBar::tab {
                background: #21262d;
                color: #8b949e;
                padding: 12px 24px;
                margin-right: 4px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: bold;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a6b3c, stop:1 #2d9e60);
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background: #2d9e60;
                color: white;
            }
        """

    @staticmethod
    def get_scroll_bar_style() -> str:
        """获取增强的滚动条样式"""
        return """
            QScrollBar:vertical {
                background: #21262d;
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a6b3c, stop:1 #2d9e60);
                min-height: 30px;
                border-radius: 6px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2d9e60, stop:1 #1a6b3c);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background: #21262d;
                height: 12px;
                border-radius: 6px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a6b3c, stop:1 #2d9e60);
                min-width: 30px;
                border-radius: 6px;
                margin: 2px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """

    @staticmethod
    def apply_status_color(widget, status: str):
        """根据状态设置颜色"""
        colors = {
            "正常": "#3fb950",
            "黄色预警": "#ffd700",
            "橙色预警": "#ff9800",
            "红色预警": "#f85149"
        }

        color = colors.get(status, "#58a6ff")

        if hasattr(widget, 'setStyleSheet'):
            current_style = widget.styleSheet()
            widget.setStyleSheet(f"{current_style}; color: {color}; font-weight: bold;")


class AnimationManager:
    """动画管理器"""

    @staticmethod
    def fade_in(widget, duration: int = 300, callback: Optional[Callable] = None):
        """淡入动画"""
        effect = widget.graphicsEffect()
        if effect is None:
            from PyQt5.QtWidgets import QGraphicsOpacityEffect
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)

        animation = QPropertyAnimation(effect, b"opacity")
        animation.setDuration(duration)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

        if callback:
            animation.finished.connect(callback)

        animation.start()

    @staticmethod
    def slide_in(widget, direction: str = "left", duration: int = 300, callback: Optional[Callable] = None):
        """滑入动画"""
        # 简化实现，仅作为示例
        # 实际需要更复杂的实现
        if callback:
            QTimer.singleShot(duration, callback)

    @staticmethod
    def pulse(widget, duration: int = 200):
        """脉冲动画（用于预警提醒）"""
        # 简化实现
        if hasattr(widget, 'setStyleSheet'):
            original_style = widget.styleSheet()
            widget.setStyleSheet(f"{original_style}; background-color: rgba(248, 81, 73, 0.3);")
            QTimer.singleShot(duration, lambda: widget.setStyleSheet(original_style))
